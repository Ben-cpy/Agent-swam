# Plan: Project Structure Refactor + tasks/1.md Update

## Part 1: Minimal Structural Refactoring

### Change 1: Rename `backend/api/models.py` → `backend/api/ai_models.py`
- **Why**: naming conflict with `backend/models.py` (DB models); dev already uses awkward alias `from api import models as models_api`
- **Files to update**:
  - `backend/api/models.py` → rename to `backend/api/ai_models.py` (no content change)
  - `backend/main.py`: `from api import models as models_api` → `from api import ai_models as models_api`

### Change 2: Rename `backend/core/backends/` → `backend/core/adapters/`
- **Why**: directory name "backends" is ambiguous; the classes inside are all named `*Adapter`, making `adapters/` the correct name
- **Files to update**:
  - Rename directory `backend/core/backends/` → `backend/core/adapters/`
  - `backend/core/executor.py`: `from core.backends import ...` → `from core.adapters import ...`
  - `tests/verify_m1_fixes.py`: `from core.backends.claude_code` → `from core.adapters.claude_code` (2 lines)
  - Internal relative imports inside the directory stay unchanged

### Change 3: Rename `tasks/1.md` → `tasks/requirements.md`
- **Why**: filename "1.md" is meaningless; content is project requirements
- No code/import changes needed

### No-op decisions (keep as-is):
- `backend/runner/agent.py` - single-file package is intentional for future multi-runner expansion
- `log.md`, `tasks.db`, `tmp/` in root - already gitignored, runtime artifacts
- `PROGRESS.md` - keep in root, not worth moving

---

## Part 2: Update `tasks/requirements.md` (was `tasks/1.md`)

Rewrite with concise bullet points. Two sections: **Implemented** and **Planned**.

### Implemented:
- Kanban board (TODO/RUNNING/DONE/FAILED) with real-time SWR polling
- Task creation: title, prompt, model, permission mode, workspace selection
- Per-task git worktree isolation (auto branch `task-{id}`, cleanup on delete)
- Cancel / retry / continue tasks
- Claude Code backend adapter (stream-json, usage tracking, quota detection)
- OpenAI Codex backend adapter (JSONL, usage tracking)
- Model selection per task (Claude models + Codex o3/o4-mini)
- Claude permission modes (plan, bypassPermissions, acceptEdits, etc.)
- Local workspace support (filesystem path)
- SSH workspace support (remote host + directory)
- SSH container workspace support (via SSH into Docker containers)
- Serial execution per workspace (1 task at a time)
- Real-time log streaming via SSE with auto-reconnect
- GPU + RAM resource monitoring (nvidia-smi / wmic / free)
- Usage aggregation dashboard (cost + tokens)
- WebSocket terminal access for SSH tasks (xterm.js + tmux)
- Runner heartbeat registration (local runner auto-registers on startup)

### Planned / Not Yet Implemented:
- Parallel task execution using git worktrees (multiple tasks concurrently per workspace)
- GPU resource conflict detection across workspaces sharing the same server
- Task auto-splitting: break large tasks into subtasks
- Process summarization / context pruning to prevent context bloat
- Proper DB migration system (currently manual ALTER TABLE)
- Authentication / API key protection
- Pagination + virtual scroll for long task/log lists
- Structured logging + monitoring/alerting

---

## Execution Order

1. Rename `tasks/1.md` → `tasks/requirements.md`, rewrite content
2. Rename `backend/api/models.py` → `backend/api/ai_models.py`, update `backend/main.py`
3. Rename dir `backend/core/backends/` → `backend/core/adapters/`, update `executor.py` + `tests/verify_m1_fixes.py`

## Verification

- Start backend: `cd backend && uvicorn main:app` — no import errors
- Check frontend still builds: `cd frontend && npm run build`
- Run test: `python tests/verify_m1_fixes.py`
- Confirm GET `/api/models` endpoint still works
