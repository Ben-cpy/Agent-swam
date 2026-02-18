from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from database import get_db
from models import Run

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def get_usage(db: AsyncSession = Depends(get_db)):
    """Aggregate usage statistics from all Run records that have usage_json."""
    result = await db.execute(
        select(Run).where(Run.usage_json.isnot(None))
    )
    runs = result.scalars().all()

    total_cost_usd = 0.0
    total_tokens = 0
    total_input_tokens = 0
    total_output_tokens = 0

    by_backend: dict = {
        "claude_code": {"runs": 0, "cost_usd": 0.0, "tokens": 0},
        "codex_cli": {"runs": 0, "cost_usd": 0.0, "tokens": 0},
    }

    for run in runs:
        try:
            usage = json.loads(run.usage_json)
        except (json.JSONDecodeError, TypeError):
            continue

        backend_key = run.backend  # e.g. "claude_code" or "codex_cli"

        if backend_key not in by_backend:
            by_backend[backend_key] = {"runs": 0, "cost_usd": 0.0, "tokens": 0}

        by_backend[backend_key]["runs"] += 1

        # Claude: cost_usd / total_cost_usd, duration_ms, num_turns
        cost = usage.get("cost_usd") or usage.get("total_cost_usd") or 0.0
        total_cost_usd += cost
        by_backend[backend_key]["cost_usd"] += cost

        # Codex: input_tokens, output_tokens, total_tokens
        inp = usage.get("input_tokens", 0) or 0
        out = usage.get("output_tokens", 0) or 0
        tok = usage.get("total_tokens", inp + out) or 0

        total_input_tokens += inp
        total_output_tokens += out
        total_tokens += tok
        by_backend[backend_key]["tokens"] += tok

    return {
        "runs_count": len(runs),
        "total_cost_usd": round(total_cost_usd, 6),
        "total_tokens": total_tokens,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "by_backend": by_backend,
    }
