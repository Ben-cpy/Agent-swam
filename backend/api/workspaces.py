from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from database import get_db
from models import Workspace, Runner
from schemas import WorkspaceCreate, WorkspaceResponse
import os

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    workspace: WorkspaceCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new workspace"""
    # Validate path exists
    if not os.path.exists(workspace.path):
        raise HTTPException(status_code=400, detail="Workspace path does not exist")

    # Check if path already exists
    result = await db.execute(
        select(Workspace).where(Workspace.path == workspace.path)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="Workspace with this path already exists")

    runner_result = await db.execute(
        select(Runner).where(Runner.runner_id == workspace.runner_id)
    )
    runner = runner_result.scalar_one_or_none()
    if not runner:
        raise HTTPException(status_code=400, detail="Runner not found")

    new_workspace = Workspace(
        path=workspace.path,
        display_name=workspace.display_name,
        runner_id=workspace.runner_id,
        concurrency_limit=1  # M1: fixed to 1
    )

    db.add(new_workspace)
    await db.commit()
    await db.refresh(new_workspace)

    return new_workspace


@router.get("", response_model=List[WorkspaceResponse])
async def list_workspaces(db: AsyncSession = Depends(get_db)):
    """List all workspaces"""
    result = await db.execute(select(Workspace))
    workspaces = result.scalars().all()

    return workspaces


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific workspace by ID"""
    result = await db.execute(
        select(Workspace).where(Workspace.workspace_id == workspace_id)
    )
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return workspace
