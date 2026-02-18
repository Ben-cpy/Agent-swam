from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from database import get_db
from models import Workspace, Runner, WorkspaceType
from schemas import WorkspaceCreate, WorkspaceResponse
import os

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _build_canonical_path(workspace: WorkspaceCreate) -> str:
    if workspace.workspace_type == WorkspaceType.LOCAL:
        return os.path.abspath(os.path.normpath(workspace.path))

    if workspace.workspace_type == WorkspaceType.SSH:
        user_part = f"{workspace.ssh_user}@" if workspace.ssh_user else ""
        port = workspace.port or 22
        return f"ssh://{user_part}{workspace.host}:{port}{workspace.path}"

    user_part = f"{workspace.ssh_user}@" if workspace.ssh_user else ""
    port = workspace.port or 22
    return (
        f"ssh://{user_part}{workspace.host}:{port}"
        f"/container/{workspace.container_name}:{workspace.path}"
    )


def _validate_workspace_input(workspace: WorkspaceCreate):
    if workspace.workspace_type == WorkspaceType.LOCAL:
        if not os.path.exists(workspace.path):
            raise HTTPException(status_code=400, detail="Local workspace path does not exist")
        return

    if not workspace.host:
        raise HTTPException(status_code=400, detail="Host is required for SSH workspace")

    if workspace.workspace_type == WorkspaceType.SSH_CONTAINER and not workspace.container_name:
        raise HTTPException(status_code=400, detail="Container name is required for SSH container workspace")


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    workspace: WorkspaceCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new workspace"""
    _validate_workspace_input(workspace)
    canonical_path = _build_canonical_path(workspace)

    # Check if path already exists
    result = await db.execute(
        select(Workspace).where(Workspace.path == canonical_path)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="Workspace with this path already exists")

    runner = None
    if workspace.runner_id is not None:
        runner_result = await db.execute(
            select(Runner).where(Runner.runner_id == workspace.runner_id)
        )
        runner = runner_result.scalar_one_or_none()
        if not runner:
            raise HTTPException(status_code=400, detail="Runner not found")
    else:
        runner_result = await db.execute(
            select(Runner).order_by(Runner.runner_id.asc())
        )
        runner = runner_result.scalars().first()
        if not runner:
            raise HTTPException(status_code=400, detail="No runner available")

    new_workspace = Workspace(
        path=canonical_path,
        display_name=workspace.display_name,
        workspace_type=workspace.workspace_type,
        host=workspace.host,
        port=workspace.port,
        ssh_user=workspace.ssh_user,
        container_name=workspace.container_name,
        runner_id=runner.runner_id,
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
