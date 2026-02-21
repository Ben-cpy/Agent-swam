import asyncio
import logging
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Task, TaskStatus, Workspace, WorkspaceType

logger = logging.getLogger(__name__)


class TaskReconciler:
    """Reconciles non-running tasks with actual git/worktree state on disk.

    Important: this reconciler must not auto-advance review workflow states.
    It only fixes stale worktree references.
    """

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

            if task_changed:
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
