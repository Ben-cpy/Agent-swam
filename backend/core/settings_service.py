from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import AppSetting, Runner, Workspace

WORKSPACE_MAX_PARALLEL_KEY = "workspace_max_parallel"
DEFAULT_WORKSPACE_MAX_PARALLEL = 3
MIN_WORKSPACE_MAX_PARALLEL = 1
MAX_WORKSPACE_MAX_PARALLEL = 20


async def get_workspace_max_parallel(db: AsyncSession) -> int:
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == WORKSPACE_MAX_PARALLEL_KEY)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        return DEFAULT_WORKSPACE_MAX_PARALLEL

    try:
        value = int(setting.value)
    except (TypeError, ValueError):
        return DEFAULT_WORKSPACE_MAX_PARALLEL

    if value < MIN_WORKSPACE_MAX_PARALLEL:
        return MIN_WORKSPACE_MAX_PARALLEL
    if value > MAX_WORKSPACE_MAX_PARALLEL:
        return MAX_WORKSPACE_MAX_PARALLEL
    return value


async def set_workspace_max_parallel(db: AsyncSession, value: int) -> int:
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == WORKSPACE_MAX_PARALLEL_KEY)
    )
    setting = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if setting is None:
        setting = AppSetting(
            key=WORKSPACE_MAX_PARALLEL_KEY,
            value=str(value),
            updated_at=now,
        )
        db.add(setting)
    else:
        setting.value = str(value)
        setting.updated_at = now
    return value


async def apply_parallel_limit_globally(db: AsyncSession, limit: int) -> None:
    ws_result = await db.execute(select(Workspace))
    workspaces = ws_result.scalars().all()
    for workspace in workspaces:
        workspace.concurrency_limit = limit

    runner_result = await db.execute(select(Runner))
    runners = runner_result.scalars().all()
    for runner in runners:
        runner.max_parallel = limit
