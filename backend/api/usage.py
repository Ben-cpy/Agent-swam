from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from database import get_db
from models import Run, QuotaState
from datetime import datetime, timedelta, timezone
import json

router = APIRouter(prefix="/api/usage", tags=["usage"])


def _aggregate_runs(runs, backend_filter: str) -> dict:
    """Aggregate usage data from a list of runs for a specific backend."""
    task_count = 0
    total_cost_usd = 0.0
    total_tokens = 0

    for run in runs:
        if run.backend != backend_filter:
            continue
        task_count += 1
        if run.usage_json:
            try:
                usage = json.loads(run.usage_json)
            except (json.JSONDecodeError, TypeError):
                continue

            if backend_filter == "claude_code":
                cost = usage.get("total_cost_usd") or usage.get("cost_usd") or 0
                total_cost_usd += float(cost)
            elif backend_filter == "codex_cli":
                tokens = usage.get("total_tokens") or 0
                total_tokens += int(tokens)

    result = {"task_count": task_count}
    if backend_filter == "claude_code":
        result["total_cost_usd"] = round(total_cost_usd, 4)
    elif backend_filter == "codex_cli":
        result["total_tokens"] = total_tokens

    return result


@router.get("")
async def get_usage(db: AsyncSession = Depends(get_db)):
    """Get usage aggregation for Claude and OpenAI over 5h and weekly windows."""
    now = datetime.now(timezone.utc)
    five_hours_ago = now - timedelta(hours=5)
    one_week_ago = now - timedelta(days=7)

    # Fetch all runs in the weekly window (superset of 5h)
    result = await db.execute(
        select(Run).where(
            and_(
                Run.started_at >= one_week_ago,
                Run.ended_at.isnot(None),
            )
        )
    )
    all_runs = result.scalars().all()

    # Split into 5h and weekly sets
    runs_5h = [r for r in all_runs if r.started_at >= five_hours_ago]

    # Fetch quota states
    quota_result = await db.execute(select(QuotaState))
    quotas = {q.provider: q for q in quota_result.scalars().all()}

    def build_provider(backend_key: str, provider_key: str) -> dict:
        quota = quotas.get(provider_key)
        return {
            "5h": {
                **_aggregate_runs(runs_5h, backend_key),
                "window_start": five_hours_ago.isoformat(),
                "window_end": now.isoformat(),
            },
            "weekly": {
                **_aggregate_runs(all_runs, backend_key),
                "window_start": one_week_ago.isoformat(),
                "window_end": now.isoformat(),
            },
            "quota_state": quota.state.value if quota else "UNKNOWN",
            "last_quota_error": quota.last_event_at.isoformat() if quota and quota.last_event_at else None,
        }

    return {
        "claude": build_provider("claude_code", "claude"),
        "openai": build_provider("codex_cli", "openai"),
    }
