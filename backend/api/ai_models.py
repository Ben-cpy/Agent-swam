"""
API endpoint for listing available models per backend.
Caches model lists per backend with a 10-minute TTL.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])

# Fallback model lists when CLI is unavailable
CLAUDE_CODE_FALLBACK_MODELS = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
]
CLAUDE_CODE_DEFAULT_MODEL = "claude-sonnet-4-5"

CODEX_CLI_MODELS = ["o4-mini", "o3", "o3-mini"]
CODEX_CLI_REASONING_EFFORTS = ["low", "medium", "high"]
CODEX_CLI_DEFAULT_MODEL = "o4-mini"

COPILOT_CLI_MODELS = [
    "claude-sonnet-4.6",
    "claude-sonnet-4.5",
    "claude-haiku-4.5",
    "claude-opus-4.6",
    "claude-opus-4.5",
    "claude-sonnet-4",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5.1-codex",
    "gpt-5.1-codex-mini",
    "gpt-4.1",
    "gemini-3-pro-preview",
]
COPILOT_CLI_DEFAULT_MODEL = "claude-sonnet-4.5"

CACHE_TTL_SECONDS = 600  # 10 minutes

# In-memory cache: backend -> {"models": [...], "fetched_at": datetime}
_model_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = asyncio.Lock()


async def _fetch_claude_models() -> List[str]:
    """
    Try to get available Claude models via CLI.
    Falls back to the hardcoded list if the CLI is unavailable or errors.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            # CLI is available; return fallback list (model listing not a standard CLI flag)
            return CLAUDE_CODE_FALLBACK_MODELS
    except (FileNotFoundError, asyncio.TimeoutError, Exception) as exc:
        logger.warning("claude CLI not available, using fallback model list: %s", exc)

    return CLAUDE_CODE_FALLBACK_MODELS


def _is_cache_valid(backend: str) -> bool:
    """Return True if cached data for the given backend is still within TTL."""
    entry = _model_cache.get(backend)
    if not entry:
        return False
    fetched_at: datetime = entry["fetched_at"]
    age = datetime.now(timezone.utc) - fetched_at
    return age < timedelta(seconds=CACHE_TTL_SECONDS)


async def _get_backend_models(backend: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Return model info for a specific backend, using cache when valid.
    """
    async with _cache_lock:
        if not force_refresh and _is_cache_valid(backend):
            return _model_cache[backend]["data"]

        if backend == "claude_code":
            models = await _fetch_claude_models()
            data: Dict[str, Any] = {
                "backend": "claude_code",
                "models": models,
                "default": CLAUDE_CODE_DEFAULT_MODEL,
            }
        elif backend == "codex_cli":
            data = {
                "backend": "codex_cli",
                "models": CODEX_CLI_MODELS,
                "reasoning_efforts": CODEX_CLI_REASONING_EFFORTS,
                "default": CODEX_CLI_DEFAULT_MODEL,
            }
        elif backend == "copilot_cli":
            data = {
                "backend": "copilot_cli",
                "models": COPILOT_CLI_MODELS,
                "default": COPILOT_CLI_DEFAULT_MODEL,
            }
        else:
            data = {"backend": backend, "models": [], "default": None}

        _model_cache[backend] = {
            "data": data,
            "fetched_at": datetime.now(timezone.utc),
        }
        return data


@router.get("")
async def list_models(refresh: bool = False):
    """
    Return available models for each supported backend.

    Query params:
    - refresh: if true, bypass the cache and re-fetch model lists.

    Response:
    {
        "results": [
            {"backend": "claude_code", "models": [...], "default": "..."},
            {"backend": "codex_cli", "models": [...], "reasoning_efforts": [...], "default": "..."}
        ]
    }
    """
    backends = ["claude_code", "codex_cli", "copilot_cli"]
    results = []
    for backend in backends:
        data = await _get_backend_models(backend, force_refresh=refresh)
        results.append(data)

    return {"results": results}
