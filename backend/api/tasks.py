from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from database import get_db, async_session_maker
from models import Task, TaskStatus, Workspace, Run
from schemas import TaskCreate, TaskResponse, NextTaskNumberResponse
from core.executor import TaskExecutor
from datetime import datetime, timezone

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
    db: AsyncSession = Depends(get_db)
):
    """List all tasks, optionally filtered by status"""
    query = select(Task)

    if status:
        query = query.where(Task.status == status)

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
        select(Task).where(Task.id == task_id)
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


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a task and its related run records."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete a running task. Cancel it first.")

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

    return {"message": "Task deleted successfully"}
