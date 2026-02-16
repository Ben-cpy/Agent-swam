from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import Task, Workspace, Runner, Run, TaskStatus, ErrorClass, WorkspaceType
from core.backends import ClaudeCodeAdapter, CodexAdapter
from datetime import datetime
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes tasks using the appropriate backend adapter"""

    # Tracks running tasks that were requested to cancel.
    _cancelled_task_ids: set[int] = set()

    def __init__(self, db_session_maker):
        self.db_session_maker = db_session_maker

    async def execute_task(self, task_id: int, db: Optional[AsyncSession] = None) -> bool:
        """
        Execute a task by ID.

        Returns:
            bool: True if execution started successfully, False otherwise
        """
        if db is None:
            async with self.db_session_maker() as session:
                return await self._execute_task_with_db(task_id, session)
        return await self._execute_task_with_db(task_id, db)

    async def _execute_task_with_db(self, task_id: int, db: AsyncSession) -> bool:
        # Fetch task with workspace
        result = await db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            logger.error(f"Task {task_id} not found")
            return False

        if task.status != TaskStatus.TODO:
            logger.warning(f"Task {task_id} is not in TODO status: {task.status}")
            return False

        # Fetch workspace
        result = await db.execute(
            select(Workspace).where(Workspace.workspace_id == task.workspace_id)
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            logger.error(f"Workspace {task.workspace_id} not found")
            return False

        if workspace.workspace_type != WorkspaceType.LOCAL:
            task.status = TaskStatus.FAILED
            task.updated_at = datetime.utcnow()
            await db.commit()
            logger.error(
                "Workspace %s type %s is not executable yet (only local supported in current runner)",
                workspace.workspace_id,
                workspace.workspace_type.value,
            )
            return False

        # Fetch runner
        result = await db.execute(
            select(Runner).where(Runner.runner_id == workspace.runner_id)
        )
        runner = result.scalar_one_or_none()

        if not runner:
            logger.error(f"Runner {workspace.runner_id} not found")
            return False

        # Create run record
        run = Run(
            task_id=task.id,
            runner_id=runner.runner_id,
            backend=task.backend.value,
            started_at=datetime.utcnow()
        )
        db.add(run)
        await db.flush()

        # Update task status
        task.status = TaskStatus.RUNNING
        task.run_id = run.run_id
        task.updated_at = datetime.utcnow()
        await db.commit()

        logger.info(f"Starting task {task_id} with backend {task.backend} in workspace {workspace.path}")

        # Execute asynchronously without blocking request/scheduler session.
        asyncio.create_task(
            self._run_task(
                task_id=task.id,
                run_id=run.run_id,
                workspace_path=workspace.path,
                backend=task.backend.value,
                prompt=task.prompt,
            )
        )

        return True

    async def _run_task(
        self,
        task_id: int,
        run_id: int,
        workspace_path: str,
        backend: str,
        prompt: str,
    ):
        """
        Internal method to run the task execution.
        This runs in a background task with its own DB sessions.
        """
        try:
            # Select adapter
            if backend == "claude_code":
                adapter = ClaudeCodeAdapter(workspace_path)
            elif backend == "codex_cli":
                adapter = CodexAdapter(workspace_path)
            else:
                raise ValueError(f"Unknown backend: {backend}")

            # Execute and collect logs
            log_lines = []
            exit_code = None

            async for line in adapter.execute(
                prompt,
                should_terminate=lambda: self._is_task_marked_cancelled(task_id),
            ):
                log_lines.append(line)

                # Parse exit code from final line
                if "[Process exited with code" in line:
                    try:
                        exit_code = int(line.split("code ")[1].split("]")[0])
                    except Exception:
                        pass

            # If exit code not found, assume failure
            if exit_code is None:
                exit_code = 1

            # Determine success and error class
            success, error_class_str = adapter.parse_exit_code(exit_code)
            was_cancelled = (
                exit_code == 130
                or self._is_task_marked_cancelled(task_id)
                or await self._is_task_cancelled_in_db(task_id)
            )

            await self._persist_execution_result(
                task_id=task_id,
                run_id=run_id,
                exit_code=exit_code,
                success=success,
                error_class_str=error_class_str,
                log_blob="".join(log_lines),
                was_cancelled=was_cancelled,
            )

        except Exception as e:
            logger.error(f"Error executing task {task_id}: {e}", exc_info=True)
            await self._persist_internal_error(task_id, run_id, str(e))
        finally:
            self._cancelled_task_ids.discard(task_id)

    async def _persist_execution_result(
        self,
        task_id: int,
        run_id: int,
        exit_code: int,
        success: bool,
        error_class_str: Optional[str],
        log_blob: str,
        was_cancelled: bool,
    ):
        async with self.db_session_maker() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one_or_none()
            run_result = await db.execute(select(Run).where(Run.run_id == run_id))
            run = run_result.scalar_one_or_none()

            if not task or not run:
                logger.error(f"Task/run not found while persisting result (task={task_id}, run={run_id})")
                return

            run.ended_at = datetime.utcnow()
            if was_cancelled:
                run.exit_code = 130
                run.error_class = ErrorClass.UNKNOWN
                task.status = TaskStatus.CANCELLED
            else:
                run.exit_code = exit_code
                if success:
                    task.status = TaskStatus.DONE
                    run.error_class = None
                else:
                    task.status = TaskStatus.FAILED
                    if error_class_str and error_class_str in ErrorClass.__members__:
                        run.error_class = ErrorClass[error_class_str]
                    else:
                        run.error_class = ErrorClass.UNKNOWN

            if log_blob:
                run.log_blob = log_blob

            task.updated_at = datetime.utcnow()
            await db.commit()
            logger.info(f"Task {task_id} completed with status {task.status}")

    async def _persist_internal_error(self, task_id: int, run_id: int, error_msg: str):
        async with self.db_session_maker() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one_or_none()
            run_result = await db.execute(select(Run).where(Run.run_id == run_id))
            run = run_result.scalar_one_or_none()
            if not task or not run:
                return

            was_cancelled = task.status == TaskStatus.CANCELLED
            run.ended_at = datetime.utcnow()
            run.exit_code = 130 if was_cancelled else -1
            run.error_class = ErrorClass.UNKNOWN
            run.log_blob = f"Internal error: {error_msg}"

            if was_cancelled:
                task.status = TaskStatus.CANCELLED
            else:
                task.status = TaskStatus.FAILED

            task.updated_at = datetime.utcnow()
            await db.commit()

    async def _is_task_cancelled_in_db(self, task_id: int) -> bool:
        async with self.db_session_maker() as db:
            result = await db.execute(
                select(Task.status).where(Task.id == task_id)
            )
            status = result.scalar_one_or_none()
            return status == TaskStatus.CANCELLED

    def _is_task_marked_cancelled(self, task_id: int) -> bool:
        return task_id in self._cancelled_task_ids

    async def cancel_task(self, task_id: int, db: Optional[AsyncSession] = None) -> bool:
        """
        Cancel a running task.

        Marks task as CANCELLED and requests subprocess termination if running.

        Returns:
            bool: True if cancelled successfully
        """
        if db is None:
            async with self.db_session_maker() as session:
                return await self._cancel_task_with_db(task_id, session)
        return await self._cancel_task_with_db(task_id, db)

    async def _cancel_task_with_db(self, task_id: int, db: AsyncSession) -> bool:
        result = await db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            return False

        if task.status not in [TaskStatus.TODO, TaskStatus.RUNNING]:
            return False

        was_running = task.status == TaskStatus.RUNNING
        task.status = TaskStatus.CANCELLED
        task.updated_at = datetime.utcnow()

        if was_running:
            self._cancelled_task_ids.add(task.id)

        # If there's a run, mark it as cancelled
        if task.run_id:
            result = await db.execute(
                select(Run).where(Run.run_id == task.run_id)
            )
            run = result.scalar_one_or_none()
            if run:
                run.ended_at = datetime.utcnow()
                run.exit_code = 130  # SIGINT
                run.error_class = ErrorClass.UNKNOWN

        await db.commit()

        logger.info(f"Task {task_id} cancelled")
        return True
