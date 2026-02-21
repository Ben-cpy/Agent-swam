"""
Regression test: retry must re-queue the same FAILED task in-place.

This script is intentionally standalone (no pytest dependency).
Run with:
  python tests/test_retry_inplace.py
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone


def _prepare_import_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_path = os.path.join(project_root, "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    return backend_path


async def _run() -> None:
    with tempfile.TemporaryDirectory(prefix="retry-inplace-") as tmpdir:
        db_path = os.path.join(tmpdir, "tasks-test.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

        _prepare_import_path()

        from sqlalchemy import select, func
        from database import init_db, async_session_maker
        from models import (
            BackendType,
            Run,
            Runner,
            RunnerStatus,
            Task,
            TaskStatus,
            Workspace,
            WorkspaceType,
        )
        from api.tasks import retry_task

        await init_db()

        async with async_session_maker() as db:
            runner = Runner(
                env="test",
                capabilities=["claude_code"],
                heartbeat_at=datetime.now(timezone.utc),
                status=RunnerStatus.ONLINE,
                max_parallel=1,
            )
            db.add(runner)
            await db.flush()

            workspace = Workspace(
                path="D:/tmp/retry-test-workspace",
                display_name="retry-test-workspace",
                workspace_type=WorkspaceType.LOCAL,
                runner_id=runner.runner_id,
                concurrency_limit=1,
            )
            db.add(workspace)
            await db.flush()

            task = Task(
                title="retry-in-place",
                prompt="fix failure and retry",
                workspace_id=workspace.workspace_id,
                backend=BackendType.CLAUDE_CODE,
                status=TaskStatus.FAILED,
                branch_name="main",
                worktree_path="D:/tmp/retry-test-workspace-task-1",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(task)
            await db.flush()

            run = Run(
                task_id=task.id,
                runner_id=runner.runner_id,
                backend=task.backend.value,
                started_at=datetime.now(timezone.utc),
                ended_at=datetime.now(timezone.utc),
                exit_code=1,
            )
            db.add(run)
            await db.flush()

            task.run_id = run.run_id
            await db.commit()
            await db.refresh(task)

            task_id = task.id
            original_title = task.title
            original_worktree_path = task.worktree_path

        async with async_session_maker() as db:
            await retry_task(task_id, db=db)

        async with async_session_maker() as db:
            result = await db.execute(select(Task).where(Task.id == task_id))
            retried_task = result.scalar_one()

            count_result = await db.execute(select(func.count(Task.id)))
            task_count = int(count_result.scalar() or 0)

            assert task_count == 1, f"expected exactly 1 task, got {task_count}"
            assert retried_task.id == task_id
            assert retried_task.status == TaskStatus.TODO
            assert retried_task.run_id is None
            assert retried_task.title == original_title
            assert retried_task.worktree_path == original_worktree_path

        print("PASS: retry keeps the same task and worktree (FAILED -> TODO)")


if __name__ == "__main__":
    asyncio.run(_run())
