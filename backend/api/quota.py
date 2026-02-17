from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import QuotaState, QuotaStateValue
from schemas import QuotaStateResponse
from typing import List
from datetime import datetime

router = APIRouter(prefix="/api/quota", tags=["quota"])


@router.get("", response_model=List[QuotaStateResponse])
async def list_quota_states(db: AsyncSession = Depends(get_db)):
    """List all quota states."""
    result = await db.execute(select(QuotaState))
    return result.scalars().all()


@router.post("/{provider}/reset")
async def reset_quota(
    provider: str,
    db: AsyncSession = Depends(get_db),
):
    """Manually reset a provider's quota state to OK."""
    result = await db.execute(
        select(QuotaState).where(
            QuotaState.provider == provider,
            QuotaState.account_label == "default",
        )
    )
    qs = result.scalar_one_or_none()
    if not qs:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")

    qs.state = QuotaStateValue.OK
    qs.last_event_at = datetime.utcnow()
    qs.note = "Manually reset"
    await db.commit()

    return {"message": f"Provider '{provider}' reset to OK"}
