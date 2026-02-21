import asyncio
import logging
import os
import re
import shlex

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from database import get_db, async_session_maker
from models import Task, TaskStatus, Workspace, WorkspaceType, Run, BackendType
from schemas import TaskCreate, TaskResponse, NextTaskNumberResponse, TaskContinueRequest, TaskPatch
from core.adapters import ClaudeCodeAdapter, CodexAdapter, CopilotAdapter
from core.executor import TaskExecutor
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _set_task_for_requeue(task: Task, prompt: str, model: Optional[str] = None) -> None:
    """Prepare a task for re-execution in the same worktree, appending the new prompt to history."""
    # Build history before overwriting task.prompt
    history: list = list(task.prompt_history) if task.prompt_history else [task.prompt]
    # Only append when the prompt actually changes (continue vs retry)
    if prompt != task.prompt:
        history.append(prompt)
    task.prompt = prompt
    task.prompt_history = history
    if model is not None:
        task.model = model
    task.status = TaskStatus.TODO
    task.updated_at = datetime.now(timezone.utc)


def _get_task_branch(task_id: int) -> str:
    return f"task-{task_id}"


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    task: TaskCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new task"""
    workspace_result = await db.execute(
        select(Workspace).where(Workspace.workspace_id == task.workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=400, detail="Workspace not found")

    new_task = Task(
        title=task.title,
        prompt=task.prompt,
        prompt_history=[task.prompt],
        workspace_id=task.workspace_id,
        backend=task.backend,
        branch_name=task.branch_name,
        model=task.model,
        status=TaskStatus.TODO,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)

    return new_task


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[TaskStatus] = Query(None),
    workspace_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """List all tasks, optionally filtered by status and/or workspace"""
    query = select(Task).options(selectinload(Task.run))

    if status:
        query = query.where(Task.status == status)

    if workspace_id:
        query = query.where(Task.workspace_id == workspace_id)

    query = query.order_by(Task.created_at.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    return tasks


@router.get("/next-number", response_model=NextTaskNumberResponse)
async def get_next_task_number(
    workspace_id: int = Query(...),
    db: AsyncSession = Depends(get_db)
):
    """Get the next task number and suggested title for a workspace."""
    workspace_result = await db.execute(
        select(Workspace).where(Workspace.workspace_id == workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=400, detail="Workspace not found")

    count_result = await db.execute(
        select(func.count(Task.id)).where(Task.workspace_id == workspace_id)
    )
    count = count_result.scalar() or 0
    next_number = count + 1

    return NextTaskNumberResponse(
        next_number=next_number,
        suggested_title=f"{workspace.display_name}-{next_number}"
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific task by ID"""
    result = await db.execute(
        select(Task).options(selectinload(Task.run)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def patch_task(
    task_id: int,
    body: TaskPatch,
    db: AsyncSession = Depends(get_db)
):
    """Partially update a task (e.g. rename the title)."""
    result = await db.execute(
        select(Task).options(selectinload(Task.run)).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.title is not None:
        stripped = body.title.strip()
        if not stripped:
            raise HTTPException(status_code=422, detail="Title cannot be empty")
        task.title = stripped
        task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)

    return task


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Cancel a task"""
    executor = TaskExecutor(async_session_maker)
    success = await executor.cancel_task(task_id, db=db)

    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel task")

    return {"message": "Task cancelled successfully"}


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Retry a failed task by re-queueing the same task.
    Reuses the existing worktree and does not create a new task.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed tasks can be retried")

    previous_run_id = task.run_id
    _set_task_for_requeue(task, task.prompt, task.model)
    task.run_id = None
    logger.info(
        "Retry task in-place: task_id=%s status=FAILED->TODO run_id=%s->None worktree_path=%s",
        task_id,
        previous_run_id,
        task.worktree_path,
    )

    await db.commit()
    await db.refresh(task)

    return task


@router.post("/{task_id}/continue", response_model=TaskResponse)
async def continue_task(
    task_id: int,
    body: TaskContinueRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Continue a completed or failed task with new instructions.
    Resets the task to TODO so the scheduler picks it up again.
    The existing worktree is preserved so work continues in the same context.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in (TaskStatus.TO_BE_REVIEW, TaskStatus.DONE, TaskStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail="Only TO_BE_REVIEW, DONE or FAILED tasks can be continued"
        )

    previous_status = task.status.value if isinstance(task.status, TaskStatus) else str(task.status)
    previous_run_id = task.run_id
    _set_task_for_requeue(task, body.prompt, body.model)
    task.run_id = None
    logger.info(
        "Continue task in-place: task_id=%s status=%s->TODO run_id=%s->None worktree_path=%s",
        task_id,
        previous_status,
        previous_run_id,
        task.worktree_path,
    )

    await db.commit()
    await db.refresh(task)

    return task


@router.post("/{task_id}/merge", response_model=TaskResponse)
async def merge_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Merge task worktree branch back to base branch directly.
    On success, cleanup the task worktree and mark task as DONE.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.TO_BE_REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Only TO_BE_REVIEW tasks can be merged"
        )

    workspace_result = await db.execute(
        select(Workspace).where(Workspace.workspace_id == task.workspace_id)
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=400, detail="Workspace not found")

    target_branch = (task.branch_name or "main").strip() or "main"
    task_branch = _get_task_branch(task.id)

    try:
        if workspace.workspace_type in (WorkspaceType.SSH, WorkspaceType.SSH_CONTAINER):
            await _merge_on_ssh_workspace(
                workspace=workspace,
                task=task,
                worktree_path=task.worktree_path,
                target_branch=target_branch,
                preferred_task_branch=task_branch,
            )
        else:
            await _merge_on_local_workspace(
                workspace=workspace,
                task=task,
                worktree_path=task.worktree_path,
                target_branch=target_branch,
                preferred_task_branch=task_branch,
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if task.worktree_path:
        await _remove_worktree(task_id, task.worktree_path, workspace)

    task.status = TaskStatus.DONE
    task.worktree_path = None
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)

    return task


@router.post("/{task_id}/mark-done", response_model=TaskResponse)
async def mark_task_done(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a reviewed task as DONE manually.
    This endpoint never performs merge/cleanup automatically.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.TO_BE_REVIEW:
        raise HTTPException(
            status_code=400,
            detail="Only TO_BE_REVIEW tasks can be marked as DONE",
        )

    task.status = TaskStatus.DONE
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    logger.info("Task %s marked as DONE manually", task_id)
    return task


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a task and its related run records. Also removes the git worktree if present."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete a running task. Cancel it first.")

    # Capture worktree info before deletion so we can clean up after
    worktree_path = task.worktree_path
    workspace: Optional[Workspace] = None
    if worktree_path:
        ws_result = await db.execute(
            select(Workspace).where(Workspace.workspace_id == task.workspace_id)
        )
        workspace = ws_result.scalar_one_or_none()

    # Break potential FK cycle before deleting runs.
    task.run_id = None
    await db.flush()

    runs_result = await db.execute(
        select(Run).where(Run.task_id == task.id)
    )
    runs = runs_result.scalars().all()
    for run in runs:
        await db.delete(run)

    await db.delete(task)
    await db.commit()

    # Best-effort worktree cleanup (after DB commit so task deletion is not blocked)
    if worktree_path and workspace:
        await _remove_worktree(task_id, worktree_path, workspace)

    return {"message": "Task deleted successfully"}


async def _run_cmd_capture(cmd: list[str]) -> tuple[int, str, str]:
    """Run a subprocess command, return (returncode, stdout_text, stderr_text)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode,
        stdout.decode(errors="replace").strip(),
        stderr.decode(errors="replace").strip(),
    )


async def _run_cmd(cmd: list[str]) -> tuple[int, str]:
    """Run a subprocess command, return (returncode, stderr_text)."""
    rc, _stdout, stderr = await _run_cmd_capture(cmd)
    return rc, stderr


async def _run_ssh_cmd(ssh_target: str, cmd: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "ssh",
        ssh_target,
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode,
        stdout.decode(errors="replace").strip(),
        stderr.decode(errors="replace").strip(),
    )


def _combine_git_output(stdout: str, stderr: str) -> str:
    parts = [p.strip() for p in (stdout, stderr) if p and p.strip()]
    return " | ".join(parts)


def _extract_exit_code_from_adapter_logs(lines: list[str]) -> int:
    for line in reversed(lines):
        match = re.search(r"\[Process exited with code (-?\d+)\]", line)
        if match:
            return int(match.group(1))
    return 1


async def _has_unmerged_files_local(repo_path: str) -> bool:
    rc, out, err = await _run_cmd_capture(
        ["git", "-C", repo_path, "diff", "--name-only", "--diff-filter=U"]
    )
    if rc != 0:
        raise RuntimeError(f"Failed to inspect merge conflicts: {err}")
    return bool(out.strip())


async def _has_unmerged_files_ssh(ssh_target: str, repo_path: str) -> bool:
    rc, out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(repo_path)} diff --name-only --diff-filter=U",
    )
    if rc != 0:
        raise RuntimeError(f"Failed to inspect merge conflicts (ssh): {err}")
    return bool(out.strip())


async def _is_merge_in_progress_local(repo_path: str) -> bool:
    rc, _out, _err = await _run_cmd_capture(
        ["git", "-C", repo_path, "rev-parse", "-q", "--verify", "MERGE_HEAD"]
    )
    return rc == 0


async def _ensure_clean_base_workspace_local(workspace_path: str) -> None:
    rc, out, err = await _run_cmd_capture(["git", "-C", workspace_path, "status", "--porcelain"])
    if rc != 0:
        raise RuntimeError(f"Failed to inspect base workspace status: {err}")
    if out:
        raise RuntimeError("Base workspace has uncommitted changes; please clean it before merge")


async def _ensure_clean_base_workspace_ssh(ssh_target: str, workspace_path: str) -> None:
    rc, out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(workspace_path)} status --porcelain",
    )
    if rc != 0:
        raise RuntimeError(f"Failed to inspect base workspace status (ssh): {err}")
    if out:
        raise RuntimeError("Base workspace has uncommitted changes; please clean it before merge")


async def _resolve_task_branch_local(
    workspace_path: str,
    worktree_path: str,
    preferred_task_branch: str,
) -> str:
    rc, _out, _err = await _run_cmd_capture(
        ["git", "-C", workspace_path, "rev-parse", "--verify", preferred_task_branch]
    )
    if rc == 0:
        return preferred_task_branch

    rc, out, err = await _run_cmd_capture(
        ["git", "-C", worktree_path, "rev-parse", "--abbrev-ref", "HEAD"]
    )
    if rc != 0:
        raise RuntimeError(f"Task branch '{preferred_task_branch}' not found: {err}")
    detected_branch = out.strip()
    if not detected_branch or detected_branch == "HEAD":
        raise RuntimeError(f"Task branch '{preferred_task_branch}' not found and worktree is detached")

    rc, _out, err = await _run_cmd_capture(
        ["git", "-C", workspace_path, "rev-parse", "--verify", detected_branch]
    )
    if rc != 0:
        raise RuntimeError(
            f"Task branch '{preferred_task_branch}' not found and detected branch '{detected_branch}' is invalid: {err}"
        )
    logger.warning(
        "Preferred task branch '%s' missing, fallback to detected branch '%s'",
        preferred_task_branch,
        detected_branch,
    )
    return detected_branch


async def _resolve_task_branch_ssh(
    ssh_target: str,
    workspace_path: str,
    worktree_path: str,
    preferred_task_branch: str,
) -> str:
    rc, _out, _err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(workspace_path)} rev-parse --verify {shlex.quote(preferred_task_branch)}",
    )
    if rc == 0:
        return preferred_task_branch

    rc, out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(worktree_path)} rev-parse --abbrev-ref HEAD",
    )
    if rc != 0:
        raise RuntimeError(f"Task branch '{preferred_task_branch}' not found: {err}")
    detected_branch = out.strip()
    if not detected_branch or detected_branch == "HEAD":
        raise RuntimeError(f"Task branch '{preferred_task_branch}' not found and worktree is detached")

    rc, _out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(workspace_path)} rev-parse --verify {shlex.quote(detected_branch)}",
    )
    if rc != 0:
        raise RuntimeError(
            f"Task branch '{preferred_task_branch}' not found and detected branch '{detected_branch}' is invalid: {err}"
        )
    logger.warning(
        "Preferred task branch '%s' missing on ssh workspace, fallback to detected branch '%s'",
        preferred_task_branch,
        detected_branch,
    )
    return detected_branch


async def _auto_commit_worktree_changes_local(worktree_path: str, task_id: int) -> bool:
    rc, out, err = await _run_cmd_capture(["git", "-C", worktree_path, "status", "--porcelain"])
    if rc != 0:
        raise RuntimeError(f"Failed to inspect task worktree status: {err}")
    if not out:
        return False

    rc, _out, err = await _run_cmd_capture(["git", "-C", worktree_path, "add", "-A"])
    if rc != 0:
        raise RuntimeError(f"Failed to stage task worktree changes before merge: {err}")

    commit_msg = f"chore(task-{task_id}): auto-commit pending changes before merge"
    rc, _out, err = await _run_cmd_capture(["git", "-C", worktree_path, "commit", "-m", commit_msg])
    if rc != 0:
        rc2, out2, err2 = await _run_cmd_capture(["git", "-C", worktree_path, "status", "--porcelain"])
        if rc2 != 0:
            raise RuntimeError(f"Failed to verify auto-commit result: {err2}")
        if out2:
            raise RuntimeError(f"Failed to auto-commit task worktree changes: {err}")
        return False

    logger.info("Task %s: auto-committed pending worktree changes before merge", task_id)
    return True


async def _auto_commit_worktree_changes_ssh(
    ssh_target: str,
    worktree_path: str,
    task_id: int,
) -> bool:
    rc, out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(worktree_path)} status --porcelain",
    )
    if rc != 0:
        raise RuntimeError(f"Failed to inspect task worktree status (ssh): {err}")
    if not out:
        return False

    rc, _out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(worktree_path)} add -A",
    )
    if rc != 0:
        raise RuntimeError(f"Failed to stage task worktree changes before merge (ssh): {err}")

    commit_msg = shlex.quote(f"chore(task-{task_id}): auto-commit pending changes before merge")
    rc, _out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(worktree_path)} commit -m {commit_msg}",
    )
    if rc != 0:
        rc2, out2, err2 = await _run_ssh_cmd(
            ssh_target,
            f"git -C {shlex.quote(worktree_path)} status --porcelain",
        )
        if rc2 != 0:
            raise RuntimeError(f"Failed to verify auto-commit result (ssh): {err2}")
        if out2:
            raise RuntimeError(f"Failed to auto-commit task worktree changes (ssh): {err}")
        return False

    logger.info("Task %s: auto-committed pending worktree changes before merge (ssh)", task_id)
    return True


def _build_merge_adapter(task: Task, workspace_path: str):
    backend_value = (
        task.backend.value if isinstance(task.backend, BackendType) else str(task.backend)
    )
    if backend_value == BackendType.CLAUDE_CODE.value:
        return ClaudeCodeAdapter(
            workspace_path=workspace_path,
            model=task.model,
            permission_mode=task.permission_mode,
        )
    if backend_value == BackendType.CODEX_CLI.value:
        return CodexAdapter(workspace_path=workspace_path, model=task.model)
    if backend_value == BackendType.COPILOT_CLI.value:
        return CopilotAdapter(workspace_path=workspace_path, model=task.model)
    raise RuntimeError(f"Unsupported backend for AI merge fallback: {backend_value}")


async def _resolve_merge_conflicts_with_ai_local(
    task: Task,
    workspace: Workspace,
    target_branch: str,
    task_branch: str,
    merge_error: str,
) -> None:
    adapter = _build_merge_adapter(task=task, workspace_path=workspace.path)
    prompt = (
        "You are resolving a git merge conflict in an existing repository.\n"
        f"Repository path: {workspace.path}\n"
        f"Current branch: {target_branch}\n"
        f"Merging branch: {task_branch}\n"
        f"Task id: {task.id}\n"
        f"Task title: {task.title}\n"
        f"Task prompt: {task.prompt}\n\n"
        "Current state:\n"
        "- A merge is already in progress and has conflicts.\n"
        "- Do NOT run git reset/rebase/checkout to discard changes.\n"
        "- Resolve conflicts with the best integrated code.\n"
        "- Stage resolved files.\n"
        "- Complete merge commit (git commit --no-edit is acceptable).\n"
        "- After finishing, ensure there are no unmerged files.\n\n"
        f"Original merge error: {merge_error}\n"
    )

    logs: list[str] = []
    async for line in adapter.execute(prompt):
        logs.append(line.rstrip())
    exit_code = _extract_exit_code_from_adapter_logs(logs)
    if exit_code != 0:
        raise RuntimeError(f"AI conflict resolution failed with exit code {exit_code}")

    if await _has_unmerged_files_local(workspace.path):
        raise RuntimeError("AI conflict resolution finished but unresolved files still exist")

    if await _is_merge_in_progress_local(workspace.path):
        rc, out, err = await _run_cmd_capture(["git", "-C", workspace.path, "commit", "--no-edit"])
        if rc != 0:
            raise RuntimeError(
                f"AI resolved conflicts but failed to finalize merge commit: {_combine_git_output(out, err)}"
            )


async def _merge_on_local_workspace(
    workspace: Workspace,
    task: Task,
    worktree_path: str,
    target_branch: str,
    preferred_task_branch: str,
) -> None:
    await _auto_commit_worktree_changes_local(worktree_path=worktree_path, task_id=task.id)
    await _ensure_clean_base_workspace_local(workspace.path)

    rc, _out, err = await _run_cmd_capture(["git", "-C", workspace.path, "rev-parse", "--verify", target_branch])
    if rc != 0:
        raise RuntimeError(f"Base branch '{target_branch}' not found: {err}")

    task_branch = await _resolve_task_branch_local(
        workspace_path=workspace.path,
        worktree_path=worktree_path,
        preferred_task_branch=preferred_task_branch,
    )

    rc, _out, err = await _run_cmd_capture(["git", "-C", workspace.path, "checkout", target_branch])
    if rc != 0:
        raise RuntimeError(f"Failed to checkout base branch '{target_branch}': {err}")

    rc, out, err = await _run_cmd_capture(
        ["git", "-C", workspace.path, "merge", "--ff-only", task_branch]
    )
    if rc == 0:
        return

    rc, out, err = await _run_cmd_capture(
        ["git", "-C", workspace.path, "merge", "--no-ff", "--no-edit", task_branch]
    )
    if rc == 0:
        return

    if await _has_unmerged_files_local(workspace.path):
        logger.warning(
            "Merge conflict detected for task %s, invoking backend '%s' for AI-assisted resolution",
            task.id,
            task.backend,
        )
        try:
            await _resolve_merge_conflicts_with_ai_local(
                task=task,
                workspace=workspace,
                target_branch=target_branch,
                task_branch=task_branch,
                merge_error=_combine_git_output(out, err),
            )
            return
        except RuntimeError as ai_exc:
            await _run_cmd_capture(["git", "-C", workspace.path, "merge", "--abort"])
            raise RuntimeError(str(ai_exc)) from ai_exc

    await _run_cmd_capture(["git", "-C", workspace.path, "merge", "--abort"])
    raise RuntimeError(f"Merge failed: {_combine_git_output(out, err)}")


async def _merge_on_ssh_workspace(
    workspace: Workspace,
    task: Task,
    worktree_path: Optional[str],
    target_branch: str,
    preferred_task_branch: str,
) -> None:
    if not workspace.host:
        raise RuntimeError("SSH workspace host is missing")

    ssh_target = (
        f"{workspace.ssh_user}@{workspace.host}" if workspace.ssh_user else workspace.host
    )

    if worktree_path:
        await _auto_commit_worktree_changes_ssh(
            ssh_target=ssh_target,
            worktree_path=worktree_path,
            task_id=task.id,
        )
    await _ensure_clean_base_workspace_ssh(ssh_target=ssh_target, workspace_path=workspace.path)

    rc, _out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(workspace.path)} rev-parse --verify {shlex.quote(target_branch)}",
    )
    if rc != 0:
        raise RuntimeError(f"Base branch '{target_branch}' not found: {err}")

    task_branch = await _resolve_task_branch_ssh(
        ssh_target=ssh_target,
        workspace_path=workspace.path,
        worktree_path=worktree_path,
        preferred_task_branch=preferred_task_branch,
    )

    rc, _out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(workspace.path)} checkout {shlex.quote(target_branch)}",
    )
    if rc != 0:
        raise RuntimeError(f"Failed to checkout base branch '{target_branch}': {err}")

    rc, _out, _err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(workspace.path)} merge --ff-only {shlex.quote(task_branch)}",
    )
    if rc == 0:
        return

    rc, _out, err = await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(workspace.path)} merge --no-ff --no-edit {shlex.quote(task_branch)}",
    )
    if rc == 0:
        return

    if await _has_unmerged_files_ssh(ssh_target=ssh_target, repo_path=workspace.path):
        await _run_ssh_cmd(
            ssh_target,
            f"git -C {shlex.quote(workspace.path)} merge --abort",
        )
        raise RuntimeError(
            "Merge has conflicts in SSH workspace. "
            "AI-assisted conflict resolution is currently supported for local workspaces only."
        )

    await _run_ssh_cmd(
        ssh_target,
        f"git -C {shlex.quote(workspace.path)} merge --abort",
    )
    raise RuntimeError(f"Merge failed: {err}")


async def _remove_worktree(task_id: int, worktree_path: str, workspace: Workspace) -> None:
    """Remove a git worktree directory and its associated branch.

    Each step is attempted independently so a partial failure does not
    prevent subsequent cleanup.  All errors are logged as warnings.
    """
    is_ssh = workspace.workspace_type in (WorkspaceType.SSH, WorkspaceType.SSH_CONTAINER)
    branch_name = f"task-{task_id}"

    if is_ssh:
        if not workspace.host:
            logger.warning(
                "SSH workspace %s has no host; skipping worktree removal", workspace.workspace_id
            )
            return
        ssh_target = (
            f"{workspace.ssh_user}@{workspace.host}" if workspace.ssh_user else workspace.host
        )

        # Step 1: remove the worktree directory
        rc, err = await _run_cmd(
            ["ssh", ssh_target,
             f"git worktree remove --force {shlex.quote(worktree_path)}"]
        )
        if rc != 0:
            logger.warning(
                "git worktree remove failed for task %s (ssh): %s", task_id, err
            )

        rc, err = await _run_cmd(
            ["ssh", ssh_target,
             f"git -C {shlex.quote(workspace.path)} worktree prune"]
        )
        if rc != 0:
            logger.warning(
                "git worktree prune failed for task %s (ssh): %s", task_id, err
            )

        # Step 2: delete the task branch from the main repo
        rc, err = await _run_cmd(
            ["ssh", ssh_target,
             f"git -C {shlex.quote(workspace.path)} branch -D {shlex.quote(branch_name)}"]
        )
        if rc != 0:
            logger.warning(
                "git branch -D %s failed for task %s (ssh): %s", branch_name, task_id, err
            )

    else:
        # Step 1: remove the worktree directory
        rc, err = await _run_cmd(
            ["git", "-C", workspace.path, "worktree", "remove", "--force", worktree_path]
        )
        if rc != 0:
            logger.warning(
                "git worktree remove failed for task %s: %s", task_id, err
            )

        rc, err = await _run_cmd(
            ["git", "-C", workspace.path, "worktree", "prune"]
        )
        if rc != 0:
            logger.warning(
                "git worktree prune failed for task %s: %s", task_id, err
            )

        if os.path.isdir(worktree_path):
            try:
                if not os.listdir(worktree_path):
                    os.rmdir(worktree_path)
            except OSError as exc:
                logger.warning(
                    "Failed to remove stale worktree directory %s for task %s: %s",
                    worktree_path,
                    task_id,
                    exc,
                )

        # Step 2: delete the task branch from the main repo
        rc, err = await _run_cmd(
            ["git", "-C", workspace.path, "branch", "-D", branch_name]
        )
        if rc != 0:
            logger.warning(
                "git branch -D %s failed for task %s: %s", branch_name, task_id, err
            )
