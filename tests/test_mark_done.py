"""
Regression test for manual task completion endpoint.

Run with:
  python tests/test_mark_done.py
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone


def _prepare_import_path() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_path = os.path.join(project_root, "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


async def _run() -> None:
    with tempfile.TemporaryDirectory(prefix="task-mark-done-") as tmpdir:
        db_path = os.path.join(tmpdir, "tasks-test.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

        _prepare_import_path()

        from fastapi import HTTPException
        from sqlalchemy import select

        from api.tasks import mark_task_done
        from database import async_session_maker, init_db
        from models import (
            BackendType,
            Runner,
            RunnerStatus,
            Task,
            TaskStatus,
            Workspace,
            WorkspaceType,
        )

        await init_db()

        async with async_session_maker() as db:
            runner = Runner(
                env="test",
                capabilities=["claude_code"],
                heartbeat_at=datetime.now(timezone.utc),
                status=RunnerStatus.ONLINE,
                max_parallel=2,
            )
            db.add(runner)
            await db.flush()

            workspace = Workspace(
                path=tmpdir,
                display_name="mark-done-workspace",
                workspace_type=WorkspaceType.LOCAL,
                runner_id=runner.runner_id,
                concurrency_limit=1,
            )
            db.add(workspace)
            await db.flush()

            review_task = Task(
                title="review-task",
                prompt="ready for manual finish",
                workspace_id=workspace.workspace_id,
                backend=BackendType.CLAUDE_CODE,
                status=TaskStatus.TO_BE_REVIEW,
                branch_name="main",
                worktree_path=f"{tmpdir}/repo-task-1",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(review_task)

            failed_task = Task(
                title="failed-task",
                prompt="cannot mark done directly",
                workspace_id=workspace.workspace_id,
                backend=BackendType.CLAUDE_CODE,
                status=TaskStatus.FAILED,
                branch_name="main",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(failed_task)
            await db.flush()
            await db.commit()

            review_task_id = review_task.id
            failed_task_id = failed_task.id

        async with async_session_maker() as db:
            response = await mark_task_done(review_task_id, db=db)
            assert response.status == TaskStatus.DONE
            assert response.worktree_path == f"{tmpdir}/repo-task-1"

            row = await db.execute(select(Task).where(Task.id == review_task_id))
            task_after = row.scalar_one()
            assert task_after.status == TaskStatus.DONE
            assert task_after.worktree_path == f"{tmpdir}/repo-task-1"

        async with async_session_maker() as db:
            try:
                await mark_task_done(failed_task_id, db=db)
            except HTTPException as exc:
                assert exc.status_code == 400
            else:
                raise AssertionError("expected mark_task_done to reject non-TO_BE_REVIEW task")

        print("PASS: mark-done endpoint requires TO_BE_REVIEW and does not auto-merge/cleanup")


if __name__ == "__main__":
    asyncio.run(_run())
