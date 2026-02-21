import asyncio
import json
import logging
import os
import shlex
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters import ClaudeCodeAdapter, CodexAdapter, CopilotAdapter
from models import ErrorClass, Run, Runner, Task, TaskStatus, Workspace, WorkspaceType

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Executes tasks using the appropriate backend adapter."""

    _cancelled_task_ids: set[int] = set()

    def __init__(self, db_session_maker):
        self.db_session_maker = db_session_maker

    async def _detect_current_branch(self, workspace_path: str) -> str:
        cmd = ["git", "-C", workspace_path, "rev-parse", "--abbrev-ref", "HEAD"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"Failed to detect branch: {stderr.decode(errors='replace').strip()}")
        branch = stdout.decode(errors="replace").strip()
        if not branch:
            raise RuntimeError("Failed to detect branch: empty output")
        return branch

    async def _branch_exists(self, workspace_path: str, branch_name: str) -> bool:
        """Check if a git branch exists in the given workspace."""
        process = await asyncio.create_subprocess_exec(
            "git", "-C", workspace_path, "rev-parse", "--verify", branch_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return process.returncode == 0

    async def _is_valid_git_worktree(self, worktree_path: str) -> bool:
        if not os.path.isdir(worktree_path):
            return False
        git_marker = os.path.join(worktree_path, ".git")
        if not os.path.exists(git_marker):
            return False
        process = await asyncio.create_subprocess_exec(
            "git", "-C", worktree_path, "rev-parse", "--is-inside-work-tree",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return process.returncode == 0

    def _pick_recovery_worktree_path(self, path: str) -> str:
        candidate = f"{path}-recovered"
        idx = 1
        while os.path.exists(candidate):
            candidate = f"{path}-recovered-{idx}"
            idx += 1
        return candidate

    async def _create_worktree(self, task_id: int, workspace_path: str, base_branch: str, target_path: Optional[str] = None) -> str:
        """Create or reuse a git worktree for a task."""
        worktree_path = target_path or f"{workspace_path}-task-{task_id}"
        worktree_branch = f"task-{task_id}"

        # Existing path: reuse only if it's a valid git worktree.
        if os.path.isdir(worktree_path):
            if await self._is_valid_git_worktree(worktree_path):
                logger.info(
                    "Worktree directory already exists at %s for task %s, reusing",
                    worktree_path,
                    task_id,
                )
                return worktree_path

            try:
                is_empty_dir = len(os.listdir(worktree_path)) == 0
            except OSError:
                is_empty_dir = False

            if is_empty_dir:
                os.rmdir(worktree_path)
                logger.warning(
                    "Removed empty invalid worktree directory %s for task %s",
                    worktree_path,
                    task_id,
                )
            else:
                fallback_path = self._pick_recovery_worktree_path(worktree_path)
                logger.warning(
                    "Path %s is not a valid worktree for task %s; using fallback path %s",
                    worktree_path,
                    task_id,
                    fallback_path,
                )
                worktree_path = fallback_path
        elif os.path.exists(worktree_path):
            fallback_path = self._pick_recovery_worktree_path(worktree_path)
            logger.warning(
                "Path %s is not a directory for task %s; using fallback path %s",
                worktree_path,
                task_id,
                fallback_path,
            )
            worktree_path = fallback_path

        if await self._branch_exists(workspace_path, worktree_branch):
            cmd = ["git", "-C", workspace_path, "worktree", "add", worktree_path, worktree_branch]
            logger.info(
                "Branch %s already exists; checking it out into %s for task %s",
                worktree_branch,
                worktree_path,
                task_id,
            )
        else:
            cmd = [
                "git", "-C", workspace_path,
                "worktree", "add",
                "-b", worktree_branch,
                worktree_path,
                base_branch,
            ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {stderr.decode(errors='replace').strip()}")
        logger.info(
            "Created worktree for task %s at %s",
            task_id,
            worktree_path,
        )
        return worktree_path

    async def execute_task(self, task_id: int, db: Optional[AsyncSession] = None) -> bool:
        if db is None:
            async with self.db_session_maker() as session:
                return await self._execute_task_with_db(task_id, session)
        return await self._execute_task_with_db(task_id, db)

    async def _execute_task_with_db(self, task_id: int, db: AsyncSession) -> bool:
        task_result = await db.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one_or_none()
        if not task:
            logger.error("Task %s not found", task_id)
            return False

        if task.status != TaskStatus.TODO:
            logger.warning("Task %s is not in TODO status: %s", task_id, task.status)
            return False

        workspace_result = await db.execute(
            select(Workspace).where(Workspace.workspace_id == task.workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()
        if not workspace:
            logger.error("Workspace %s not found", task.workspace_id)
            return False

        is_ssh_workspace = workspace.workspace_type in (WorkspaceType.SSH, WorkspaceType.SSH_CONTAINER)

        runner_result = await db.execute(
            select(Runner).where(Runner.runner_id == workspace.runner_id)
        )
        runner = runner_result.scalar_one_or_none()
        if not runner:
            logger.error("Runner %s not found", workspace.runner_id)
            return False

        if is_ssh_workspace:
            # SSH workspace: run task in a tmux session on the remote host
            ssh_host = workspace.host
            if not ssh_host:
                task.status = TaskStatus.FAILED
                task.updated_at = datetime.now(timezone.utc)
                await db.commit()
                logger.error("SSH workspace %s has no host configured", workspace.workspace_id)
                return False

            tmux_session_name = f"aitask-{task_id}"
            run = Run(
                task_id=task.id,
                runner_id=runner.runner_id,
                backend=task.backend.value,
                started_at=datetime.now(timezone.utc),
                tmux_session=tmux_session_name,
            )
            db.add(run)
            await db.flush()

            task.status = TaskStatus.RUNNING
            task.run_id = run.run_id
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Starting SSH task %s on host %s in tmux session %s",
                task_id,
                ssh_host,
                tmux_session_name,
            )

            asyncio.create_task(
                self._run_ssh_task(
                    task_id=task.id,
                    run_id=run.run_id,
                    ssh_host=ssh_host,
                    workspace_path=workspace.path,
                    backend=task.backend.value,
                    prompt=task.prompt,
                    tmux_session=tmux_session_name,
                    permission_mode=task.permission_mode,
                )
            )
            return True

        # Local workspace: detect branch and create worktree
        if not task.branch_name:
            try:
                task.branch_name = await self._detect_current_branch(workspace.path)
                logger.info("Auto-detected base branch '%s' for task %s", task.branch_name, task_id)
            except Exception as exc:
                task.branch_name = "main"
                logger.warning(
                    "Failed to auto-detect base branch for task %s, fallback to 'main': %s",
                    task_id,
                    exc,
                )
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()

        try:
            desired_path = task.worktree_path
            worktree_path = await self._create_worktree(
                task_id,
                workspace.path,
                task.branch_name,
                target_path=desired_path,
            )
            if task.worktree_path != worktree_path:
                task.worktree_path = worktree_path
                task.updated_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error("Task %s failed before execution due to worktree error: %s", task_id, exc)
            return False

        run = Run(
            task_id=task.id,
            runner_id=runner.runner_id,
            backend=task.backend.value,
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        task.status = TaskStatus.RUNNING
        task.run_id = run.run_id
        task.updated_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "Starting task %s with backend %s in worktree %s",
            task_id,
            task.backend,
            task.worktree_path,
        )

        asyncio.create_task(
            self._run_task(
                task_id=task.id,
                run_id=run.run_id,
                workspace_path=task.worktree_path or workspace.path,
                backend=task.backend.value,
                prompt=task.prompt,
                model=task.model,
                permission_mode=task.permission_mode,
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
        model: Optional[str] = None,
        permission_mode: Optional[str] = None,
    ):
        try:
            if backend == "claude_code":
                adapter = ClaudeCodeAdapter(workspace_path, model=model, permission_mode=permission_mode)
            elif backend == "codex_cli":
                adapter = CodexAdapter(workspace_path, model=model)
            elif backend == "copilot_cli":
                adapter = CopilotAdapter(workspace_path, model=model)
            else:
                raise ValueError(f"Unknown backend: {backend}")

            log_lines = []
            exit_code = None
            last_flush_time = asyncio.get_event_loop().time()
            flushed_blob_len = 0

            async def _flush_logs_to_db():
                nonlocal last_flush_time, flushed_blob_len
                current_blob = "".join(log_lines)
                if len(current_blob) <= flushed_blob_len:
                    return
                try:
                    async with self.db_session_maker() as flush_db:
                        run_res = await flush_db.execute(select(Run).where(Run.run_id == run_id))
                        run_obj = run_res.scalar_one_or_none()
                        if run_obj and not run_obj.ended_at:
                            run_obj.log_blob = current_blob
                            await flush_db.commit()
                    flushed_blob_len = len(current_blob)
                except Exception as flush_exc:
                    logger.warning("Failed to flush logs for run %s: %s", run_id, flush_exc)
                last_flush_time = asyncio.get_event_loop().time()

            async for line in adapter.execute(
                prompt,
                should_terminate=lambda: self._is_task_marked_cancelled(task_id),
            ):
                log_lines.append(line)
                if "[Process exited with code" in line:
                    try:
                        exit_code = int(line.split("code ")[1].split("]")[0])
                    except Exception:
                        pass

                # Flush logs to DB every 2 seconds so the SSE endpoint can stream them in real time
                now = asyncio.get_event_loop().time()
                if now - last_flush_time >= 2.0:
                    await _flush_logs_to_db()

            if exit_code is None:
                exit_code = 1

            success, error_class_str = adapter.parse_exit_code(exit_code)
            was_cancelled = exit_code == 130 or self._is_task_marked_cancelled(task_id)

            await self._persist_execution_result(
                task_id=task_id,
                run_id=run_id,
                exit_code=exit_code,
                success=success,
                error_class_str=error_class_str,
                log_blob="".join(log_lines),
                was_cancelled=was_cancelled,
                usage_data=adapter.usage_data,
                is_quota_error=adapter.is_quota_error,
            )
        except Exception as exc:
            logger.error("Error executing task %s: %s", task_id, exc, exc_info=True)
            await self._persist_internal_error(task_id, run_id, str(exc))
        finally:
            self._cancelled_task_ids.discard(task_id)

    async def _run_ssh_task(
        self,
        task_id: int,
        run_id: int,
        ssh_host: str,
        workspace_path: str,
        backend: str,
        prompt: str,
        tmux_session: str,
        permission_mode: Optional[str] = None,
    ):
        """Run a task on a remote SSH host using tmux for session persistence."""
        try:
            log_file = f"/tmp/{tmux_session}.log"

            if backend == "claude_code":
                if not permission_mode or permission_mode == "bypassPermissions":
                    perm_flag = "--dangerously-skip-permissions"
                else:
                    perm_flag = f"--permission-mode {shlex.quote(permission_mode)}"
                cli_cmd = f"claude -p --output-format stream-json {perm_flag} {shlex.quote(prompt)}"
            elif backend == "codex_cli":
                cli_cmd = f"codex -p {shlex.quote(prompt)}"
            elif backend == "copilot_cli":
                cli_cmd = f"copilot -p {shlex.quote(prompt)} --allow-all --no-color --no-alt-screen"
            else:
                raise ValueError(f"Unknown backend: {backend}")

            # Build the tmux command: create a new session running the CLI, piping output to a log file
            # The session is kept alive after the command finishes (tmux default behavior)
            tmux_cmd = (
                f"tmux new-session -d -s {shlex.quote(tmux_session)} "
                f"'({cli_cmd}) 2>&1 | tee {shlex.quote(log_file)}; "
                f"echo EXIT_CODE:$? >> {shlex.quote(log_file)}'"
            )

            # Launch the tmux session on the remote host
            launch_proc = await asyncio.create_subprocess_exec(
                "ssh", ssh_host, tmux_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await launch_proc.communicate()
            if launch_proc.returncode != 0:
                err_msg = stderr.decode(errors="replace").strip()
                raise RuntimeError(f"Failed to start SSH tmux session: {err_msg}")

            logger.info("SSH tmux session %s started on %s", tmux_session, ssh_host)

            # Stream the log file from the remote host via tail -f
            tail_proc = await asyncio.create_subprocess_exec(
                "ssh", ssh_host, f"tail -f {shlex.quote(log_file)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            log_lines = []
            exit_code = None
            last_flush_time = asyncio.get_event_loop().time()
            flushed_blob_len = 0

            async def _flush_ssh_logs_to_db():
                nonlocal last_flush_time, flushed_blob_len
                current_blob = "".join(log_lines)
                if len(current_blob) <= flushed_blob_len:
                    return
                try:
                    async with self.db_session_maker() as flush_db:
                        run_res = await flush_db.execute(select(Run).where(Run.run_id == run_id))
                        run_obj = run_res.scalar_one_or_none()
                        if run_obj and not run_obj.ended_at:
                            run_obj.log_blob = current_blob
                            await flush_db.commit()
                    flushed_blob_len = len(current_blob)
                except Exception as flush_exc:
                    logger.warning("Failed to flush SSH logs for run %s: %s", run_id, flush_exc)
                last_flush_time = asyncio.get_event_loop().time()

            assert tail_proc.stdout is not None
            async for raw_line in tail_proc.stdout:
                line = raw_line.decode(errors="replace")
                log_lines.append(line)

                if self._is_task_marked_cancelled(task_id):
                    tail_proc.terminate()
                    # Kill tmux session on remote
                    await asyncio.create_subprocess_exec(
                        "ssh", ssh_host,
                        f"tmux kill-session -t {shlex.quote(tmux_session)} 2>/dev/null || true",
                    )
                    break

                if line.startswith("EXIT_CODE:"):
                    try:
                        exit_code = int(line.strip().split("EXIT_CODE:")[1])
                    except Exception:
                        exit_code = 1
                    tail_proc.terminate()
                    break

                # Flush logs to DB every 2 seconds so the SSE endpoint can stream them in real time
                now = asyncio.get_event_loop().time()
                if now - last_flush_time >= 2.0:
                    await _flush_ssh_logs_to_db()

            if exit_code is None:
                exit_code = 1

            success = exit_code == 0
            error_class_str = None if success else "UNKNOWN"
            was_cancelled = self._is_task_marked_cancelled(task_id)

            await self._persist_execution_result(
                task_id=task_id,
                run_id=run_id,
                exit_code=exit_code,
                success=success and not was_cancelled,
                error_class_str=error_class_str,
                log_blob="".join(log_lines),
                was_cancelled=was_cancelled,
            )
        except Exception as exc:
            logger.error("Error executing SSH task %s: %s", task_id, exc, exc_info=True)
            await self._persist_internal_error(task_id, run_id, str(exc))
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
        usage_data: Optional[dict] = None,
        is_quota_error: bool = False,
    ):
        async with self.db_session_maker() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one_or_none()
            run_result = await db.execute(select(Run).where(Run.run_id == run_id))
            run = run_result.scalar_one_or_none()
            if not task or not run:
                logger.error("Task/run not found while persisting result (task=%s, run=%s)", task_id, run_id)
                return

            run.ended_at = datetime.now(timezone.utc)
            if usage_data:
                run.usage_json = json.dumps(usage_data)

            if was_cancelled:
                run.exit_code = 130
                run.error_class = ErrorClass.UNKNOWN
                task.status = TaskStatus.FAILED
            elif is_quota_error:
                run.exit_code = exit_code
                run.error_class = ErrorClass.QUOTA
                task.status = TaskStatus.FAILED
            else:
                run.exit_code = exit_code
                if success:
                    task.status = TaskStatus.TO_BE_REVIEW
                    run.error_class = None
                else:
                    task.status = TaskStatus.FAILED
                    if error_class_str and error_class_str in ErrorClass.__members__:
                        run.error_class = ErrorClass[error_class_str]
                    else:
                        run.error_class = ErrorClass.UNKNOWN

            if log_blob:
                run.log_blob = log_blob

            task.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Task %s completed with status %s", task_id, task.status)

    async def _persist_internal_error(self, task_id: int, run_id: int, error_msg: str):
        async with self.db_session_maker() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one_or_none()
            run_result = await db.execute(select(Run).where(Run.run_id == run_id))
            run = run_result.scalar_one_or_none()
            if not task or not run:
                return

            was_cancelled = self._is_task_marked_cancelled(task_id)
            run.ended_at = datetime.now(timezone.utc)
            run.exit_code = 130 if was_cancelled else -1
            run.error_class = ErrorClass.UNKNOWN
            run.log_blob = f"Internal error: {error_msg}"

            task.status = TaskStatus.FAILED
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()

    def _is_task_marked_cancelled(self, task_id: int) -> bool:
        return task_id in self._cancelled_task_ids

    async def cancel_task(self, task_id: int, db: Optional[AsyncSession] = None) -> bool:
        if db is None:
            async with self.db_session_maker() as session:
                return await self._cancel_task_with_db(task_id, session)
        return await self._cancel_task_with_db(task_id, db)

    async def _cancel_task_with_db(self, task_id: int, db: AsyncSession) -> bool:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return False

        if task.status not in [TaskStatus.TODO, TaskStatus.RUNNING]:
            return False

        was_running = task.status == TaskStatus.RUNNING
        task.status = TaskStatus.FAILED
        task.updated_at = datetime.now(timezone.utc)

        if was_running:
            self._cancelled_task_ids.add(task.id)

        if task.run_id:
            result = await db.execute(select(Run).where(Run.run_id == task.run_id))
            run = result.scalar_one_or_none()
            if run:
                run.ended_at = datetime.now(timezone.utc)
                run.exit_code = 130
                run.error_class = ErrorClass.UNKNOWN

        await db.commit()
        logger.info("Task %s cancelled (mapped to FAILED)", task_id)
        return True
