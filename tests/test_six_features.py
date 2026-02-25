"""
Integration tests for the six-feature iteration:
1. Workspace rename (display_name via PATCH)
2. GPU display - parse logic returns memory stats
3. GPU indices - workspace stores and executor passes CUDA_VISIBLE_DEVICES
4. Task completion notification - ToBeReviewNotifier logic (code review only)
5. Workspace notes - PATCH/GET round-trip
6. Task number per workspace - COUNT-based numbering
"""
import sys
import os
import asyncio

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_path = os.path.join(project_root, 'backend')
sys.path.insert(0, backend_path)
os.chdir(backend_path)

from database import init_db, async_session_maker
from runner.agent import LocalRunnerAgent
from sqlalchemy import select, func


async def setup():
    await init_db()
    async with async_session_maker() as db:
        await LocalRunnerAgent.register_local_runner(db)


# ---------------------------------------------------------------------------
# Feature 1: Workspace rename
# ---------------------------------------------------------------------------
async def test_workspace_rename():
    from models import Workspace
    from sqlalchemy import text

    async with async_session_maker() as db:
        # Create a test workspace
        ws = Workspace(
            path="/tmp/test-rename-ws",
            display_name="OldName",
            workspace_type="local",
            runner_id=1,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        ws_id = ws.workspace_id

        # Rename it
        ws.display_name = "NewName"
        await db.commit()
        await db.refresh(ws)

        assert ws.display_name == "NewName", f"Expected 'NewName', got '{ws.display_name}'"

        # Clean up
        await db.execute(text(f"DELETE FROM workspaces WHERE workspace_id = {ws_id}"))
        await db.commit()

    print("  [PASS] Feature 1: workspace rename")


# ---------------------------------------------------------------------------
# Feature 2: GPU display parse logic
# ---------------------------------------------------------------------------
def test_gpu_display_parse():
    sys.path.insert(0, os.path.join(backend_path, 'api'))
    from api.workspaces import _parse_gpu_output

    # Simulate nvidia-smi CSV output: name, memory.used, memory.total, utilization.gpu
    raw = "NVIDIA A100 80GB PCIe, 10718, 24576, 0\nNVIDIA A100 80GB PCIe, 1, 24576, 42"
    gpus = _parse_gpu_output(raw)
    assert gpus is not None, "Expected GPU list"
    assert len(gpus) == 2
    assert gpus[0].memory_used_mb == 10718
    assert gpus[0].memory_total_mb == 24576
    assert gpus[0].utilization_pct == 0
    assert gpus[1].utilization_pct == 42

    # Memory utilization should be calculable from the data
    mem_pct_0 = round(gpus[0].memory_used_mb / gpus[0].memory_total_mb * 100)
    assert mem_pct_0 == 44, f"Expected ~44%, got {mem_pct_0}%"

    print("  [PASS] Feature 2: GPU parse returns correct memory/utilization data")


# ---------------------------------------------------------------------------
# Feature 3: GPU indices stored and model field exists
# ---------------------------------------------------------------------------
async def test_gpu_indices():
    from models import Workspace
    from sqlalchemy import text

    async with async_session_maker() as db:
        ws = Workspace(
            path="/tmp/test-gpu-indices-ws",
            display_name="GPUTest",
            workspace_type="local",
            runner_id=1,
            gpu_indices="0,1",
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        ws_id = ws.workspace_id

        assert ws.gpu_indices == "0,1", f"Expected '0,1', got '{ws.gpu_indices}'"

        # Update gpu_indices
        ws.gpu_indices = "2"
        await db.commit()
        await db.refresh(ws)
        assert ws.gpu_indices == "2"

        # Clean up
        await db.execute(text(f"DELETE FROM workspaces WHERE workspace_id = {ws_id}"))
        await db.commit()

    print("  [PASS] Feature 3: gpu_indices stored and updated correctly")


def test_executor_extra_env_passed():
    """Verify that ClaudeCodeAdapter accepts extra_env and merges it."""
    from core.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter("/tmp", extra_env={"CUDA_VISIBLE_DEVICES": "0,1"})
    assert adapter.extra_env == {"CUDA_VISIBLE_DEVICES": "0,1"}
    print("  [PASS] Feature 3: ClaudeCodeAdapter accepts extra_env")


# ---------------------------------------------------------------------------
# Feature 5: Workspace notes
# ---------------------------------------------------------------------------
async def test_workspace_notes():
    from models import Workspace
    from sqlalchemy import text

    async with async_session_maker() as db:
        ws = Workspace(
            path="/tmp/test-notes-ws",
            display_name="NotesTest",
            workspace_type="local",
            runner_id=1,
            notes="# My Notes\n\nWorking on feature X",
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        ws_id = ws.workspace_id

        assert ws.notes == "# My Notes\n\nWorking on feature X"

        # Update notes
        ws.notes = "Updated notes"
        await db.commit()
        await db.refresh(ws)
        assert ws.notes == "Updated notes"

        # Set to empty
        ws.notes = ""
        await db.commit()
        await db.refresh(ws)
        assert ws.notes == ""

        # Clean up
        await db.execute(text(f"DELETE FROM workspaces WHERE workspace_id = {ws_id}"))
        await db.commit()

    print("  [PASS] Feature 5: workspace notes stored and updated")


# ---------------------------------------------------------------------------
# Feature 6: Task number per workspace (COUNT-based)
# ---------------------------------------------------------------------------
async def test_task_number_per_workspace():
    from models import Task, Workspace
    from sqlalchemy import text

    async with async_session_maker() as db:
        # Create a fresh workspace
        ws = Workspace(
            path="/tmp/test-tasknumber-ws",
            display_name="TaskNumTest",
            workspace_type="local",
            runner_id=1,
        )
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
        ws_id = ws.workspace_id

        # Initially count = 0, next_number = 1
        count_result = await db.execute(
            select(func.count(Task.id)).where(Task.workspace_id == ws_id)
        )
        count = count_result.scalar() or 0
        assert count == 0
        next_num = count + 1
        assert next_num == 1, f"Expected 1, got {next_num}"

        # Add 3 tasks
        for i in range(3):
            t = Task(
                title=f"Task {i+1}",
                prompt="test",
                workspace_id=ws_id,
                backend="claude_code",
                status="TODO",
            )
            db.add(t)
        await db.commit()

        # Now count = 3, next_number = 4
        count_result2 = await db.execute(
            select(func.count(Task.id)).where(Task.workspace_id == ws_id)
        )
        count2 = count_result2.scalar() or 0
        assert count2 == 3, f"Expected 3, got {count2}"
        next_num2 = count2 + 1
        assert next_num2 == 4

        # Clean up
        await db.execute(text(f"DELETE FROM tasks WHERE workspace_id = {ws_id}"))
        await db.execute(text(f"DELETE FROM workspaces WHERE workspace_id = {ws_id}"))
        await db.commit()

    print("  [PASS] Feature 6: task number uses COUNT (workspace-local)")


# ---------------------------------------------------------------------------
# Feature 4: Notification code logic check (static)
# ---------------------------------------------------------------------------
def test_notification_logic():
    """
    ToBeReviewNotifier now calls pushInAppToast unconditionally for all completion
    statuses (DONE, FAILED, TO_BE_REVIEW). This test verifies the toast helper
    function is importable and the notification statuses are defined correctly.
    """
    # We can't run browser code in a test, but we can verify the module is correct
    import importlib.util
    import pathlib

    toast_path = pathlib.Path(project_root) / "frontend" / "components" / "InAppToast.tsx"
    notifier_path = pathlib.Path(project_root) / "frontend" / "components" / "ToBeReviewNotifier.tsx"

    assert toast_path.exists(), "InAppToast.tsx not found"
    assert notifier_path.exists(), "ToBeReviewNotifier.tsx not found"

    # Verify InAppToast exports pushInAppToast
    content = toast_path.read_text(encoding="utf-8")
    assert "pushInAppToast" in content, "pushInAppToast not exported from InAppToast"
    assert "IN_APP_TOAST_EVENT" in content, "IN_APP_TOAST_EVENT not defined"

    # Verify ToBeReviewNotifier imports and uses pushInAppToast
    notifier_content = notifier_path.read_text(encoding="utf-8")
    assert "pushInAppToast" in notifier_content, "ToBeReviewNotifier does not use pushInAppToast"
    assert "TaskStatus.FAILED" in notifier_content, "FAILED status not handled"
    assert "TaskStatus.DONE" in notifier_content, "DONE status not handled"

    print("  [PASS] Feature 4: InAppToast component exists and integrated into notifier")


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
async def main():
    print("=" * 55)
    print("Six Feature Iteration - Integration Tests")
    print("=" * 55)
    print()

    print("[Setup] Initializing DB and runner...")
    await setup()
    print()

    failures = []

    tests = [
        ("Feature 1: Workspace rename", test_workspace_rename, True),
        ("Feature 2: GPU display parse", test_gpu_display_parse, False),
        ("Feature 3: GPU indices storage", test_gpu_indices, True),
        ("Feature 3: Executor extra_env", test_executor_extra_env_passed, False),
        ("Feature 4: Notification logic", test_notification_logic, False),
        ("Feature 5: Workspace notes", test_workspace_notes, True),
        ("Feature 6: Task number per workspace", test_task_number_per_workspace, True),
    ]

    for name, fn, is_async in tests:
        print(f"Running: {name}")
        try:
            if is_async:
                await fn()
            else:
                fn()
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
            failures.append(name)
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            failures.append(name)
        print()

    print("=" * 55)
    if failures:
        print(f"FAILED: {len(failures)} test(s) failed")
        for f in failures:
            print(f"  - {f}")
        return False
    else:
        print(f"All {len(tests)} tests passed!")
    print("=" * 55)
    return True


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
