"""
Regression test: reconcile dangling task/worktree references.

Run with:
  python tests/test_task_reconciler_orphans.py
"""

import asyncio
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


def _prepare_import_path() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_path = os.path.join(project_root, "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def _run_git(args: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


async def _run() -> None:
    with tempfile.TemporaryDirectory(prefix="task-reconciler-") as tmpdir:
        db_path = os.path.join(tmpdir, "tasks-test.db").replace("\\", "/")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

        repo_path = os.path.join(tmpdir, "repo")
        os.makedirs(repo_path, exist_ok=True)

        _run_git(["init", "-b", "main"], cwd=repo_path)
        _run_git(["config", "user.email", "test@example.com"], cwd=repo_path)
        _run_git(["config", "user.name", "Task Reconciler Test"], cwd=repo_path)

        base_file = os.path.join(repo_path, "README.md")
        with open(base_file, "w", encoding="utf-8") as f:
            f.write("base\n")
        _run_git(["add", "README.md"], cwd=repo_path)
        _run_git(["commit", "-m", "base"], cwd=repo_path)

        _prepare_import_path()

        from core.task_reconciler import TaskReconciler
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
                path=repo_path,
                display_name="task-reconciler-workspace",
                workspace_type=WorkspaceType.LOCAL,
                runner_id=runner.runner_id,
                concurrency_limit=2,
            )
            db.add(workspace)
            await db.flush()

            review_task = Task(
                title="review-task",
                prompt="already merged outside web",
                workspace_id=workspace.workspace_id,
                backend=BackendType.CLAUDE_CODE,
                status=TaskStatus.TO_BE_REVIEW,
                branch_name="main",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(review_task)
            await db.flush()

            review_worktree = f"{repo_path}-task-{review_task.id}"
            review_task.worktree_path = review_worktree

            todo_task = Task(
                title="todo-with-empty-dir",
                prompt="cleanup invalid path",
                workspace_id=workspace.workspace_id,
                backend=BackendType.CLAUDE_CODE,
                status=TaskStatus.TODO,
                branch_name="main",
                worktree_path=os.path.join(tmpdir, "dangling-empty-dir"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(todo_task)
            await db.commit()

            review_task_id = review_task.id
            todo_task_id = todo_task.id
            empty_dir = todo_task.worktree_path

        assert empty_dir is not None
        os.makedirs(empty_dir, exist_ok=True)

        _run_git(
            ["worktree", "add", "-b", f"task-{review_task_id}", review_worktree, "main"],
            cwd=repo_path,
        )
        feature_file = os.path.join(review_worktree, "feature.txt")
        with open(feature_file, "w", encoding="utf-8") as f:
            f.write("done outside web\n")
        _run_git(["add", "feature.txt"], cwd=review_worktree)
        _run_git(["commit", "-m", "task change"], cwd=review_worktree)
        _run_git(["checkout", "main"], cwd=repo_path)
        _run_git(["merge", "--no-ff", "--no-edit", f"task-{review_task_id}"], cwd=repo_path)
        _run_git(["worktree", "remove", "--force", review_worktree], cwd=repo_path)

        reconciler = TaskReconciler(async_session_maker)
        async with async_session_maker() as db:
            changed = await reconciler.reconcile_once(db=db)
        assert changed >= 2, f"expected >=2 reconciled tasks, got {changed}"

        async with async_session_maker() as db:
            from sqlalchemy import select

            review_row = await db.execute(select(Task).where(Task.id == review_task_id))
            review_after = review_row.scalar_one()
            assert review_after.status == TaskStatus.TO_BE_REVIEW
            assert review_after.worktree_path is None

            todo_row = await db.execute(select(Task).where(Task.id == todo_task_id))
            todo_after = todo_row.scalar_one()
            assert todo_after.status == TaskStatus.TODO
            assert todo_after.worktree_path is None

        branch_check = _run_git(
            ["rev-parse", "--verify", f"task-{review_task_id}"],
            cwd=repo_path,
            check=False,
        )
        assert branch_check.returncode == 0, "expected reconciler to keep task branch for manual review"

        print("PASS: dangling task worktree references are reconciled without auto-closing review tasks")


if __name__ == "__main__":
    asyncio.run(_run())
