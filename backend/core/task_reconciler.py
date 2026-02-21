import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Task, TaskStatus, Workspace, WorkspaceType

logger = logging.getLogger(__name__)


class TaskReconciler:
    """Reconciles non-running tasks with actual git/worktree state on disk."""

    def __init__(self, db_session_maker):
        self.db_session_maker = db_session_maker

    async def reconcile_once(self, db: Optional[AsyncSession] = None) -> int:
        if db is None:
            async with self.db_session_maker() as session:
                return await self._reconcile_with_db(session)
        return await self._reconcile_with_db(db)

    async def _reconcile_with_db(self, db: AsyncSession) -> int:
        result = await db.execute(
            select(Task, Workspace)
            .join(Workspace, Workspace.workspace_id == Task.workspace_id)
            .where(Task.status != TaskStatus.RUNNING)
            .order_by(Task.id.asc())
        )
        rows = result.all()

        changed_count = 0
        for task, workspace in rows:
            if workspace.workspace_type != WorkspaceType.LOCAL:
                continue

            task_changed = False
            task_branch = f"task-{task.id}"
            workspace_path = workspace.path

            if task.worktree_path:
                if await self._should_clear_worktree_path(workspace_path, task.worktree_path):
                    logger.info(
                        "Task %s worktree reference cleared (invalid/stale): %s",
                        task.id,
                        task.worktree_path,
                    )
                    task.worktree_path = None
                    task_changed = True

            # If task is waiting for review but branch is already merged/deleted outside web,
            # auto-close it so it no longer stays in TO_BE_REVIEW forever.
            if task.status == TaskStatus.TO_BE_REVIEW:
                # Re-read status and updated_at directly from DB (column projection)
                # to bypass the stale SQLAlchemy identity map. The bulk load at the
                # top of the loop captured a snapshot; the executor may have
                # committed a fresh TO_BE_REVIEW with a new updated_at since then.
                fresh = await db.execute(
                    select(Task.status, Task.updated_at).where(Task.id == task.id)
                )
                fresh_row = fresh.one_or_none()

                eligible_for_autoclose = False
                if fresh_row is not None:
                    fresh_status, fresh_updated_at = fresh_row
                    if fresh_status == TaskStatus.TO_BE_REVIEW:
                        # Grace period: skip auto-close for tasks updated within the
                        # last 60 s so a freshly-completed run isn't immediately swept
                        # away before the user has a chance to interact with it.
                        now_utc = datetime.now(timezone.utc)
                        updated_dt = fresh_updated_at
                        if updated_dt.tzinfo is None:
                            updated_dt = updated_dt.replace(tzinfo=timezone.utc)
                        if (now_utc - updated_dt).total_seconds() >= 60:
                            eligible_for_autoclose = True

                if eligible_for_autoclose:
                    branch_state = await self._get_branch_state(
                        workspace_path=workspace_path,
                        task_branch=task_branch,
                        base_branch=(task.branch_name or "main").strip() or "main",
                    )
                    if branch_state in ("merged", "missing"):
                        if task.worktree_path:
                            await self._cleanup_worktree_reference(workspace_path, task.worktree_path)
                            task.worktree_path = None
                        await self._delete_branch(workspace_path, task_branch)
                        task.status = TaskStatus.DONE
                        task_changed = True
                        logger.info(
                            "Task %s auto-closed TO_BE_REVIEW->DONE (branch_state=%s)",
                            task.id,
                            branch_state,
                        )

            if task_changed:
                task.updated_at = datetime.now(timezone.utc)
                changed_count += 1

        if changed_count > 0:
            await db.commit()

        return changed_count

    async def _should_clear_worktree_path(self, workspace_path: str, worktree_path: str) -> bool:
        if not os.path.exists(worktree_path):
            await self._git_worktree_prune(workspace_path)
            return True

        if not os.path.isdir(worktree_path):
            return True

        if await self._is_valid_git_worktree(worktree_path):
            return False

        await self._cleanup_worktree_reference(workspace_path, worktree_path)
        return True

    async def _cleanup_worktree_reference(self, workspace_path: str, worktree_path: str) -> None:
        await self._run_cmd(
            ["git", "-C", workspace_path, "worktree", "remove", "--force", worktree_path]
        )
        await self._git_worktree_prune(workspace_path)

        if os.path.isdir(worktree_path):
            try:
                if not os.listdir(worktree_path):
                    os.rmdir(worktree_path)
            except OSError as exc:
                logger.warning("Failed to remove stale directory %s: %s", worktree_path, exc)

    async def _git_worktree_prune(self, workspace_path: str) -> None:
        await self._run_cmd(["git", "-C", workspace_path, "worktree", "prune"])

    async def _is_valid_git_worktree(self, worktree_path: str) -> bool:
        git_marker = os.path.join(worktree_path, ".git")
        if not os.path.exists(git_marker):
            return False
        rc, _out, _err = await self._run_cmd(
            ["git", "-C", worktree_path, "rev-parse", "--is-inside-work-tree"]
        )
        return rc == 0

    async def _get_branch_state(self, workspace_path: str, task_branch: str, base_branch: str) -> str:
        task_exists = await self._branch_exists(workspace_path, task_branch)
        if not task_exists:
            return "missing"

        base_exists = await self._branch_exists(workspace_path, base_branch)
        if not base_exists:
            return "unknown"

        rc, _out, _err = await self._run_cmd(
            ["git", "-C", workspace_path, "merge-base", "--is-ancestor", task_branch, base_branch]
        )
        if rc == 0:
            return "merged"
        if rc == 1:
            return "not_merged"
        return "unknown"

    async def _branch_exists(self, workspace_path: str, branch_name: str) -> bool:
        rc, _out, _err = await self._run_cmd(
            ["git", "-C", workspace_path, "rev-parse", "--verify", branch_name]
        )
        return rc == 0

    async def _delete_branch(self, workspace_path: str, branch_name: str) -> None:
        await self._run_cmd(["git", "-C", workspace_path, "branch", "-D", branch_name])

    async def _run_cmd(self, cmd: list[str]) -> tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            return 127, "", str(exc)

        stdout, stderr = await proc.communicate()
        return (
            proc.returncode,
            stdout.decode(errors="replace").strip(),
            stderr.decode(errors="replace").strip(),
        )
