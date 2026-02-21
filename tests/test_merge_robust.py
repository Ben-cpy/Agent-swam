"""
Regression test for robust task merge flow.

Run with:
  python tests/test_merge_robust.py
"""
import asyncio
import os
import subprocess
import sys
import tempfile


def _prepare_import_path() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_path = os.path.join(project_root, "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def _run_git(repo_path: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo_path, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _run_git_no_check(repo_path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo_path, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _setup_repo(base_dir: str) -> str:
    repo = os.path.join(base_dir, "repo")
    os.makedirs(repo, exist_ok=True)
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Merge Tester")
    _run_git(repo, "checkout", "-B", "main")
    return repo


async def _test_auto_commit_then_merge(tasks_api) -> None:
    from models import BackendType, Task, TaskStatus, Workspace, WorkspaceType

    with tempfile.TemporaryDirectory(prefix="merge-robust-auto-") as tmpdir:
        repo = _setup_repo(tmpdir)
        worktree = os.path.join(tmpdir, "repo-task-1")

        test_file = os.path.join(repo, "feature.txt")
        _write_text(test_file, "base\n")
        _run_git(repo, "add", ".")
        _run_git(repo, "commit", "-m", "base commit")

        _run_git(repo, "worktree", "add", "-b", "task-1", worktree, "main")
        _write_text(os.path.join(worktree, "feature.txt"), "base\nfrom-task-uncommitted\n")

        workspace = Workspace(
            workspace_id=1,
            path=repo,
            display_name="test",
            workspace_type=WorkspaceType.LOCAL,
            runner_id=1,
            concurrency_limit=1,
        )
        task = Task(
            id=1,
            title="auto-commit merge",
            prompt="merge test",
            workspace_id=1,
            backend=BackendType.CLAUDE_CODE,
            status=TaskStatus.TO_BE_REVIEW,
            branch_name="main",
            worktree_path=worktree,
        )

        await tasks_api._merge_on_local_workspace(
            workspace=workspace,
            task=task,
            worktree_path=worktree,
            target_branch="main",
            preferred_task_branch="task-1",
        )

        merged_content = open(test_file, "r", encoding="utf-8").read()
        assert "from-task-uncommitted" in merged_content, "expected merged content from task worktree"

        auto_commit_msg = _run_git(repo, "log", "task-1", "-1", "--pretty=%s")
        assert "auto-commit pending changes before merge" in auto_commit_msg

        print("PASS: auto-commit pending task changes before merge")


async def _test_conflict_calls_ai_fallback(tasks_api) -> None:
    from models import BackendType, Task, TaskStatus, Workspace, WorkspaceType

    with tempfile.TemporaryDirectory(prefix="merge-robust-ai-") as tmpdir:
        repo = _setup_repo(tmpdir)
        worktree = os.path.join(tmpdir, "repo-task-2")
        conflict_file = os.path.join(repo, "conflict.txt")

        _write_text(conflict_file, "shared-line\n")
        _run_git(repo, "add", ".")
        _run_git(repo, "commit", "-m", "base commit")

        _run_git(repo, "worktree", "add", "-b", "task-2", worktree, "main")
        _write_text(os.path.join(worktree, "conflict.txt"), "task-version\n")
        _run_git(worktree, "add", ".")
        _run_git(worktree, "commit", "-m", "task change")

        _write_text(conflict_file, "main-version\n")
        _run_git(repo, "add", ".")
        _run_git(repo, "commit", "-m", "main change")

        workspace = Workspace(
            workspace_id=1,
            path=repo,
            display_name="test",
            workspace_type=WorkspaceType.LOCAL,
            runner_id=1,
            concurrency_limit=1,
        )
        task = Task(
            id=2,
            title="ai merge fallback",
            prompt="resolve conflict",
            workspace_id=1,
            backend=BackendType.CODEX_CLI,
            status=TaskStatus.TO_BE_REVIEW,
            branch_name="main",
            worktree_path=worktree,
        )

        calls = {"count": 0}
        original = tasks_api._resolve_merge_conflicts_with_ai_local

        async def _fake_ai_resolver(task, workspace, target_branch, task_branch, merge_error):
            calls["count"] += 1
            _write_text(os.path.join(workspace.path, "conflict.txt"), "resolved-main-and-task\n")
            _run_git(workspace.path, "add", "conflict.txt")
            _run_git(workspace.path, "commit", "--no-edit")

        tasks_api._resolve_merge_conflicts_with_ai_local = _fake_ai_resolver
        try:
            await tasks_api._merge_on_local_workspace(
                workspace=workspace,
                task=task,
                worktree_path=worktree,
                target_branch="main",
                preferred_task_branch="task-2",
            )
        finally:
            tasks_api._resolve_merge_conflicts_with_ai_local = original

        assert calls["count"] == 1, "expected AI fallback to be called exactly once"
        resolved = open(conflict_file, "r", encoding="utf-8").read()
        assert "resolved-main-and-task" in resolved

        print("PASS: conflict path triggers AI fallback resolver")


async def _test_base_workspace_auto_commit_then_merge(tasks_api) -> None:
    from models import BackendType, Task, TaskStatus, Workspace, WorkspaceType

    with tempfile.TemporaryDirectory(prefix="merge-robust-base-") as tmpdir:
        repo = _setup_repo(tmpdir)
        worktree = os.path.join(tmpdir, "repo-task-3")
        feature_file = os.path.join(repo, "feature.txt")
        base_dirty_file = os.path.join(repo, "ops-note.txt")

        _write_text(feature_file, "base\n")
        _run_git(repo, "add", ".")
        _run_git(repo, "commit", "-m", "base commit")

        _run_git(repo, "worktree", "add", "-b", "task-3", worktree, "main")
        _write_text(os.path.join(worktree, "feature.txt"), "base\nfrom-task-commit\n")
        _run_git(worktree, "add", ".")
        _run_git(worktree, "commit", "-m", "task change")

        # Simulate user forgot to commit in base workspace before clicking Merge.
        _write_text(base_dirty_file, "pending base workspace note\n")

        workspace = Workspace(
            workspace_id=1,
            path=repo,
            display_name="test",
            workspace_type=WorkspaceType.LOCAL,
            runner_id=1,
            concurrency_limit=1,
        )
        task = Task(
            id=3,
            title="base dirty merge",
            prompt="merge with base dirty",
            workspace_id=1,
            backend=BackendType.CLAUDE_CODE,
            status=TaskStatus.TO_BE_REVIEW,
            branch_name="main",
            worktree_path=worktree,
        )

        await tasks_api._merge_on_local_workspace(
            workspace=workspace,
            task=task,
            worktree_path=worktree,
            target_branch="main",
            preferred_task_branch="task-3",
        )

        log_msgs = _run_git(repo, "log", "main", "-4", "--pretty=%s")
        assert "auto-commit pending base workspace changes before merge" in log_msgs
        merged_content = open(feature_file, "r", encoding="utf-8").read()
        assert "from-task-commit" in merged_content

        print("PASS: base workspace dirty changes are auto-committed before merge")


async def _test_merge_without_worktree_path(tasks_api) -> None:
    from models import BackendType, Task, TaskStatus, Workspace, WorkspaceType

    with tempfile.TemporaryDirectory(prefix="merge-robust-no-worktree-") as tmpdir:
        repo = _setup_repo(tmpdir)
        feature_file = os.path.join(repo, "feature.txt")

        _write_text(feature_file, "base\n")
        _run_git(repo, "add", ".")
        _run_git(repo, "commit", "-m", "base commit")

        _run_git(repo, "checkout", "-b", "task-4", "main")
        _write_text(feature_file, "base\nfrom-task-branch-only\n")
        _run_git(repo, "add", "feature.txt")
        _run_git(repo, "commit", "-m", "task branch commit")
        _run_git(repo, "checkout", "main")

        workspace = Workspace(
            workspace_id=1,
            path=repo,
            display_name="test",
            workspace_type=WorkspaceType.LOCAL,
            runner_id=1,
            concurrency_limit=1,
        )
        task = Task(
            id=4,
            title="branch only merge",
            prompt="merge with missing worktree path",
            workspace_id=1,
            backend=BackendType.CLAUDE_CODE,
            status=TaskStatus.TO_BE_REVIEW,
            branch_name="main",
            worktree_path=None,
        )

        await tasks_api._merge_on_local_workspace(
            workspace=workspace,
            task=task,
            worktree_path=None,
            target_branch="main",
            preferred_task_branch="task-4",
        )

        merged_content = open(feature_file, "r", encoding="utf-8").read()
        assert "from-task-branch-only" in merged_content

        merge_head_check = _run_git_no_check(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD")
        assert merge_head_check.returncode != 0, "merge state should be clean after branch-only merge"

        print("PASS: merge succeeds using branch ref even when worktree path is missing")


async def _run() -> None:
    _prepare_import_path()
    from api import tasks as tasks_api

    await _test_auto_commit_then_merge(tasks_api)
    await _test_conflict_calls_ai_fallback(tasks_api)
    await _test_base_workspace_auto_commit_then_merge(tasks_api)
    await _test_merge_without_worktree_path(tasks_api)
    print("ALL PASS: robust merge flow regression tests")


if __name__ == "__main__":
    asyncio.run(_run())
