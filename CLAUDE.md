# AI-Slave

An AI task orchestration platform that dispatches coding tasks to AI agents (Claude Code, OpenAI Codex) across local and SSH workspaces. Features a FastAPI backend, kanban-style frontend, per-task git worktree isolation, model selection, usage tracking, and tmux-based terminal access for SSH workspaces.

ref to [AGENTS](AGENTS.md)

## Project Structure

```
AI-slave/
├── backend/                  # Python FastAPI backend
│   ├── main.py               # App entry point, CORS, routers, lifecycle
│   ├── config.py             # Configuration (DB, API, scheduler params)
│   ├── database.py           # SQLAlchemy async DB setup
│   ├── models.py             # DB models: Task, Workspace, Runner, Run, QuotaState
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── api/                  # Route handlers
│   │   ├── tasks.py          # Task CRUD, cancel, continue, merge
│   │   ├── workspaces.py     # Workspace management, GPU/memory monitoring
│   │   ├── logs.py           # SSE log streaming endpoint
│   │   ├── ai_models.py      # Model list and quota state
│   │   ├── usage.py          # Usage statistics
│   │   └── terminal.py       # WebSocket tmux terminal for SSH workspaces
│   ├── core/                 # Business logic
│   │   ├── executor.py       # Task runner: worktree creation, adapter dispatch, log streaming
│   │   ├── scheduler.py      # Periodic TODO-task scanner and dispatcher
│   │   └── adapters/         # AI backend adapters
│   │       ├── base.py       # Abstract adapter interface
│   │       ├── claude_code.py# Claude Code CLI adapter (stream-json parsing)
│   │       ├── codex.py      # OpenAI Codex CLI adapter
│   │       └── cli_resolver.py # CLI command path resolution
│   └── runner/
│       └── agent.py          # Local runner registration
├── frontend/                 # Next.js 16 / React 19 frontend
│   ├── app/                  # App Router pages
│   │   ├── layout.tsx        # Root layout with Navbar
│   │   ├── page.tsx          # Home: workspace list
│   │   ├── tasks/new/        # New task form
│   │   ├── tasks/[id]/       # Task detail + terminal pages
│   │   └── workspaces/       # Workspace management + kanban board
│   ├── components/           # UI components
│   │   ├── TaskBoard.tsx     # Kanban board (TODO/RUNNING/DONE/FAILED)
│   │   ├── TaskCard.tsx      # Task card with status and actions
│   │   ├── LogStream.tsx     # Real-time SSE log viewer
│   │   ├── WorkspaceCard.tsx / WorkspaceManager.tsx / WorkspaceResources.tsx
│   │   ├── UsageSummary.tsx  # Token usage stats
│   │   └── ui/               # shadcn/ui primitives
│   └── lib/
│       ├── api.ts            # Axios API client
│       └── types.ts          # TypeScript type definitions
├── scripts/
│   ├── setup_env.sh          # Init Python venv and deps
│   ├── start_server.sh       # Start backend server
│   └── clean_workspace.sh    # Clean workspace data
├── tests/                    # Test files
├── docs/                     # Project documentation
├── tasks/                    # Git worktree working directories
├── tasks.db                  # SQLite database
├── AGENTS.md                 # Agent configuration docs
└── PROGRESS.md               # Development progress log
```

## Key Enums

- `TaskStatus`: TODO → RUNNING → DONE | FAILED
- `BackendType`: `claude_code`, `codex_cli`
- `WorkspaceType`: `local`, `ssh`, `ssh_container`

## Task Execution Flow

1. Frontend submits task → `POST /api/tasks` → DB status: TODO
2. Scheduler polls every 5s → dispatches tasks respecting workspace concurrency limits
3. Executor creates a git worktree on branch `task-{id}` at `{workspace_path}-task-{id}`
4. Adapter builds and runs the CLI command, streams logs via SSE
5. On completion: exit code parsed → status set to DONE/FAILED, usage saved to `usage_json`

## Dev Commands

```bash
# Backend
uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Frontend
cd frontend && npm run dev   # http://localhost:3000
```

## Tech Stack

| Layer    | Tech                          |
|----------|-------------------------------|
| Backend  | FastAPI, SQLAlchemy (async), SQLite/aiosqlite |
| Frontend | Next.js 16, React 19, SWR, Tailwind CSS, xterm.js |
| AI       | Claude Code CLI / OpenAI Codex CLI |
| Isolation| Git worktrees (one per task)  |
| SSH      | asyncssh + tmux sessions      |
