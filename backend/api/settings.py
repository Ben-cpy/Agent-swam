from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.settings_service import (
    apply_parallel_limit_globally,
    get_workspace_max_parallel,
    set_workspace_max_parallel,
)
from database import get_db
from schemas import AppSettingsResponse, AppSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    workspace_max_parallel = await get_workspace_max_parallel(db)
    return AppSettingsResponse(workspace_max_parallel=workspace_max_parallel)


@router.put("", response_model=AppSettingsResponse)
async def update_settings(
    payload: AppSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    await set_workspace_max_parallel(db, payload.workspace_max_parallel)
    await apply_parallel_limit_globally(db, payload.workspace_max_parallel)
    await db.commit()
    return AppSettingsResponse(workspace_max_parallel=payload.workspace_max_parallel)
