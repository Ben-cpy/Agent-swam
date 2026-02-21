"""
Regression tests for quota false positives.

Run with:
  python tests/test_quota_false_positive.py
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
    _prepare_import_path()

    from core.adapters.copilot import CopilotAdapter

    adapter = CopilotAdapter(workspace_path="D:/tmp/quota-false-positive")
    adapter._scan_for_quota_keywords("Read docs\\FRONTEND.md lines 429-431")
    assert not adapter.is_quota_error, "line-number 429 must not be treated as quota error"

    adapter._scan_for_quota_keywords("HTTP 429 Too Many Requests")
    assert adapter.is_quota_error, "real 429 rate-limit signal must be detected"

    with tempfile.TemporaryDirectory(prefix="quota-false-positive-") as tmpdir:
        db_path = os.path.join(tmpdir, "tasks-test.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

        from sqlalchemy import select
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
        from core.executor import TaskExecutor

        await init_db()

        async with async_session_maker() as db:
            runner = Runner(
                env="test",
                capabilities=["copilot_cli"],
                heartbeat_at=datetime.now(timezone.utc),
                status=RunnerStatus.ONLINE,
                max_parallel=1,
            )
            db.add(runner)
            await db.flush()

            workspace = Workspace(
                path="D:/tmp/quota-false-positive-workspace",
                display_name="quota-false-positive-workspace",
                workspace_type=WorkspaceType.LOCAL,
                runner_id=runner.runner_id,
                concurrency_limit=1,
            )
            db.add(workspace)
            await db.flush()

            task = Task(
                title="quota-false-positive",
                prompt="noop",
                workspace_id=workspace.workspace_id,
                backend=BackendType.COPILOT_CLI,
                status=TaskStatus.RUNNING,
                branch_name="main",
                worktree_path="D:/tmp/quota-false-positive-worktree",
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
            )
            db.add(run)
            await db.flush()
            await db.commit()

            task_id = task.id
            run_id = run.run_id

        executor = TaskExecutor(async_session_maker)
        await executor._persist_execution_result(
            task_id=task_id,
            run_id=run_id,
            exit_code=0,
            success=True,
            error_class_str=None,
            log_blob="ok\n",
            was_cancelled=False,
            usage_data=None,
            is_quota_error=True,
        )

        async with async_session_maker() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            updated_task = task_result.scalar_one()
            run_result = await db.execute(select(Run).where(Run.run_id == run_id))
            updated_run = run_result.scalar_one()

            assert updated_task.status == TaskStatus.TO_BE_REVIEW
            assert updated_run.exit_code == 0
            assert updated_run.error_class is None

    print("PASS: quota false positives no longer force FAILED on successful runs")


if __name__ == "__main__":
    asyncio.run(_run())
