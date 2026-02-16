from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from database import get_db
from models import Runner
from schemas import RunnerResponse

router = APIRouter(prefix="/api/runners", tags=["runners"])


@router.get("", response_model=List[RunnerResponse])
async def list_runners(db: AsyncSession = Depends(get_db)):
    """List all runners"""
    result = await db.execute(select(Runner))
    runners = result.scalars().all()

    return runners
