import asyncio
import logging
import shlex

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from database import get_db, async_session_maker
from models import Task, TaskStatus, Workspace, WorkspaceType, Run
from schemas import TaskCreate, TaskResponse, NextTaskNumberResponse, TaskContinueRequest
from core.executor import TaskExecutor
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


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
    Retry a failed task by creating a new task with the same parameters.
    The original task remains in FAILED status.
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    original_task = result.scalar_one_or_none()

    if not original_task:
        raise HTTPException(status_code=404, detail="Task not found")

    if original_task.status != TaskStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed tasks can be retried")

    # Create new task with same parameters
    new_task = Task(
        title=f"{original_task.title} (Retry)",
        prompt=original_task.prompt,
        workspace_id=original_task.workspace_id,
        backend=original_task.backend,
        branch_name=original_task.branch_name,
        model=original_task.model,
        status=TaskStatus.TODO,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)

    return new_task


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

    if task.status not in (TaskStatus.DONE, TaskStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail="Only DONE or FAILED tasks can be continued"
        )

    task.prompt = body.prompt
    if body.model is not None:
        task.model = body.model
    task.status = TaskStatus.TODO
    task.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)

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


async def _run_cmd(cmd: list) -> tuple[int, str]:
    """Run a subprocess command, return (returncode, stderr_text)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    return proc.returncode, stderr.decode(errors="replace").strip()


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
            ["git", "worktree", "remove", "--force", worktree_path]
        )
        if rc != 0:
            logger.warning(
                "git worktree remove failed for task %s: %s", task_id, err
            )

        # Step 2: delete the task branch from the main repo
        rc, err = await _run_cmd(
            ["git", "-C", workspace.path, "branch", "-D", branch_name]
        )
        if rc != 0:
            logger.warning(
                "git branch -D %s failed for task %s: %s", branch_name, task_id, err
            )
