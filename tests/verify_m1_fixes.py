"""
Verification suite for M1 review fixes (issues 1-6).
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select, text

# Resolve project paths and set backend as runtime cwd for DB URL compatibility.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_PATH = PROJECT_ROOT / "backend"
os.chdir(BACKEND_PATH)
sys.path.insert(0, str(BACKEND_PATH))

from api.tasks import create_task
from api.workspaces import create_workspace
from core.backends.claude_code import ClaudeCodeAdapter
from core.backends.codex import CodexAdapter
from core.executor import TaskExecutor
from database import async_session_maker, engine, init_db
from models import BackendType, Run, Runner, RunnerStatus, Task, TaskStatus, Workspace
from schemas import TaskCreate, WorkspaceCreate


def _print_metric(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    suffix = f" | {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")


async def _reset_database():
    await engine.dispose()
    db_file = BACKEND_PATH / "tasks.db"
    if db_file.exists():
        db_file.unlink()
    await init_db()


async def _check_foreign_keys_enabled() -> bool:
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA foreign_keys"))
        value = result.scalar()
        enabled = value == 1
        _print_metric("sqlite_foreign_keys_enabled", enabled, f"value={value}")
        return enabled


async def _seed_runner_and_workspace() -> Tuple[int, int]:
    async with async_session_maker() as db:
        runner = Runner(
            env="verify-env",
            capabilities=["codex_cli", "claude_code"],
            heartbeat_at=datetime.utcnow(),
            status=RunnerStatus.ONLINE,
            max_parallel=1,
        )
        db.add(runner)
        await db.flush()

        workspace = Workspace(
            path=str(PROJECT_ROOT),
            display_name="verify-workspace",
            runner_id=runner.runner_id,
            concurrency_limit=1,
        )
        db.add(workspace)
        await db.commit()
        await db.refresh(workspace)
        return runner.runner_id, workspace.workspace_id


async def _check_api_fk_guards() -> bool:
    ok = True
    async with async_session_maker() as db:
        try:
            await create_task(
                TaskCreate(
                    title="invalid-workspace",
                    prompt="x",
                    workspace_id=999999,
                    backend=BackendType.CLAUDE_CODE,
                ),
                db,
            )
            _print_metric("task_api_workspace_validation", False, "unexpected success")
            ok = False
        except HTTPException as exc:
            passed = exc.status_code == 400
            _print_metric("task_api_workspace_validation", passed, f"status={exc.status_code}")
            ok = ok and passed

    async with async_session_maker() as db:
        try:
            await create_workspace(
                WorkspaceCreate(
                    path=str(PROJECT_ROOT),
                    display_name="invalid-runner",
                    runner_id=999999,
                ),
                db,
            )
            _print_metric("workspace_api_runner_validation", False, "unexpected success")
            ok = False
        except HTTPException as exc:
            passed = exc.status_code == 400
            _print_metric("workspace_api_runner_validation", passed, f"status={exc.status_code}")
            ok = ok and passed

    return ok


def _check_exit_code_mapping() -> bool:
    claude = ClaudeCodeAdapter(str(PROJECT_ROOT))
    codex = CodexAdapter(str(PROJECT_ROOT))
    claude_map = claude.parse_exit_code(130)
    codex_map = codex.parse_exit_code(130)
    ok = claude_map == (False, None) and codex_map == (False, None)
    _print_metric("adapter_exit_130_mapping", ok, f"claude={claude_map}, codex={codex_map}")
    return ok


async def _create_todo_task(workspace_id: int, title: str) -> int:
    async with async_session_maker() as db:
        task = Task(
            title=title,
            prompt="run verification",
            workspace_id=workspace_id,
            backend=BackendType.CODEX_CLI,
            status=TaskStatus.TODO,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task.id


async def _fetch_task_and_run(task_id: int) -> Tuple[Task, Optional[Run]]:
    async with async_session_maker() as db:
        task_result = await db.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one()
        run = None
        if task.run_id:
            run_result = await db.execute(select(Run).where(Run.run_id == task.run_id))
            run = run_result.scalar_one_or_none()
        return task, run


async def _fake_codex_execute(self, prompt, should_terminate=None):
    for idx in range(20):
        if should_terminate and should_terminate():
            yield "\n[Process exited with code 130]\n"
            return
        await asyncio.sleep(0.05)
        yield f"log-{idx}\n"
    yield "\n[Process exited with code 0]\n"


async def _check_executor_lifecycle_and_cancel(workspace_id: int) -> bool:
    original_execute = CodexAdapter.execute
    CodexAdapter.execute = _fake_codex_execute
    ok = True

    try:
        executor = TaskExecutor(async_session_maker)

        # Session-lifecycle check: background run must complete after dispatch-session closes.
        task_id = await _create_todo_task(workspace_id, "session-lifecycle")
        async with async_session_maker() as db:
            started = await executor.execute_task(task_id, db=db)
        await asyncio.sleep(1.4)

        task, run = await _fetch_task_and_run(task_id)
        lifecycle_ok = started and task.status == TaskStatus.DONE and run is not None and run.exit_code == 0
        _print_metric(
            "executor_background_session_lifecycle",
            lifecycle_ok,
            f"started={started}, status={task.status.value}, exit={run.exit_code if run else None}",
        )
        ok = ok and lifecycle_ok

        # Cancel consistency check: cancellation should persist and not be overwritten by completion.
        cancel_task_id = await _create_todo_task(workspace_id, "cancel-consistency")
        async with async_session_maker() as db:
            started_cancel = await executor.execute_task(cancel_task_id, db=db)
        await asyncio.sleep(0.2)
        cancel_ok = await executor.cancel_task(cancel_task_id)
        await asyncio.sleep(0.8)
        cancel_task_obj, cancel_run = await _fetch_task_and_run(cancel_task_id)
        status_ok = (
            started_cancel
            and cancel_ok
            and cancel_task_obj.status == TaskStatus.CANCELLED
            and cancel_run is not None
            and cancel_run.exit_code == 130
        )
        _print_metric(
            "executor_cancel_status_consistency",
            status_ok,
            f"started={started_cancel}, cancel_ok={cancel_ok}, status={cancel_task_obj.status.value}, exit={cancel_run.exit_code if cancel_run else None}",
        )
        ok = ok and status_ok
    finally:
        CodexAdapter.execute = original_execute

    return ok


async def main() -> int:
    print("=" * 64)
    print("M1 Fix Verification")
    print("=" * 64)

    await _reset_database()
    runner_id, workspace_id = await _seed_runner_and_workspace()

    checks = []
    checks.append(await _check_foreign_keys_enabled())
    checks.append(await _check_api_fk_guards())
    checks.append(_check_exit_code_mapping())
    checks.append(await _check_executor_lifecycle_and_cancel(workspace_id))

    passed = all(checks)
    print("-" * 64)
    print(f"SUMMARY: {'PASS' if passed else 'FAIL'}")
    print(f"Seeded runner_id={runner_id}, workspace_id={workspace_id}")
    print("=" * 64)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
