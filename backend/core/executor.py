from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import Task, Workspace, Runner, Run, TaskStatus, ErrorClass
from core.backends import ClaudeCodeAdapter, CodexAdapter
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes tasks using the appropriate backend adapter"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute_task(self, task_id: int) -> bool:
        """
        Execute a task by ID.

        Returns:
            bool: True if execution started successfully, False otherwise
        """
        # Fetch task with workspace
        result = await self.db.execute(
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
        result = await self.db.execute(
            select(Workspace).where(Workspace.workspace_id == task.workspace_id)
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            logger.error(f"Workspace {task.workspace_id} not found")
            return False

        # Fetch runner
        result = await self.db.execute(
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
        self.db.add(run)
        await self.db.flush()

        # Update task status
        task.status = TaskStatus.RUNNING
        task.run_id = run.run_id
        task.updated_at = datetime.utcnow()
        await self.db.commit()

        logger.info(f"Starting task {task_id} with backend {task.backend} in workspace {workspace.path}")

        # Execute asynchronously without blocking
        asyncio.create_task(self._run_task(task, workspace, run))

        return True

    async def _run_task(self, task: Task, workspace: Workspace, run: Run):
        """
        Internal method to run the task execution.
        This runs in a background task.
        """
        try:
            # Select adapter
            if task.backend.value == "claude_code":
                adapter = ClaudeCodeAdapter(workspace.path)
            elif task.backend.value == "codex_cli":
                adapter = CodexAdapter(workspace.path)
            else:
                raise ValueError(f"Unknown backend: {task.backend}")

            # Execute and collect logs
            log_lines = []
            exit_code = None

            async for line in adapter.execute(task.prompt):
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

            # Update run record
            run.ended_at = datetime.utcnow()
            run.exit_code = exit_code
            run.log_blob = "".join(log_lines)

            if error_class_str:
                run.error_class = ErrorClass[error_class_str]

            # Update task status
            if success:
                task.status = TaskStatus.DONE
            else:
                task.status = TaskStatus.FAILED

            task.updated_at = datetime.utcnow()

            # Commit changes
            await self.db.commit()

            logger.info(f"Task {task.id} completed with status {task.status}")

        except Exception as e:
            logger.error(f"Error executing task {task.id}: {e}", exc_info=True)

            # Mark as failed
            run.ended_at = datetime.utcnow()
            run.exit_code = -1
            run.error_class = ErrorClass.UNKNOWN
            run.log_blob = f"Internal error: {str(e)}"

            task.status = TaskStatus.FAILED
            task.updated_at = datetime.utcnow()

            await self.db.commit()

    async def cancel_task(self, task_id: int) -> bool:
        """
        Cancel a running task.

        For M1, this just marks the task as CANCELLED.
        In M2+, this would send a kill signal to the running process.

        Returns:
            bool: True if cancelled successfully
        """
        result = await self.db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            return False

        if task.status not in [TaskStatus.TODO, TaskStatus.RUNNING]:
            return False

        task.status = TaskStatus.CANCELLED
        task.updated_at = datetime.utcnow()

        # If there's a run, mark it as cancelled
        if task.run_id:
            result = await self.db.execute(
                select(Run).where(Run.run_id == task.run_id)
            )
            run = result.scalar_one_or_none()
            if run:
                run.ended_at = datetime.utcnow()
                run.exit_code = 130  # SIGINT
                run.error_class = ErrorClass.CODE

        await self.db.commit()

        logger.info(f"Task {task_id} cancelled")
        return True
