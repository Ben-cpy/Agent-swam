# Frontend Architecture

AI Slave frontend: Next.js 16 (App Router) + TypeScript + Tailwind CSS v4 + shadcn/ui.

## Tech Stack

| Layer | Tech |
|-------|------|
| Framework | Next.js 16, React 19, TypeScript |
| Styling | Tailwind CSS v4, shadcn/ui |
| Data Fetching | SWR (polling), Axios |
| Terminal | xterm.js + WebSocket |
| Date Utils | date-fns |

## Project Structure

```
frontend/
├── app/                          # Next.js App Router pages
│   ├── layout.tsx               # Root layout (Navbar + ToBeReviewNotifier)
│   ├── page.tsx                 # Home: workspace list
│   ├── settings/page.tsx        # Settings: max parallel, notification toggle
│   ├── tasks/
│   │   ├── new/page.tsx         # New task form
│   │   └── [id]/
│   │       ├── page.tsx         # Task detail + logs + actions
│   │       └── terminal/page.tsx# WebSocket terminal (SSH workspaces)
│   └── workspaces/
│       ├── page.tsx             # Workspace list + create
│       └── [id]/
│           ├── board/page.tsx   # Kanban board for a workspace
│           └── tasks/page.tsx   # Task list for a workspace
│
├── components/
│   ├── Navbar.tsx               # Top navigation bar
│   ├── TaskBoard.tsx            # Kanban board (TODO/RUNNING/TO_BE_REVIEW/DONE/FAILED)
│   ├── TaskCard.tsx             # Task card with status badge and action buttons
│   ├── TaskForm.tsx             # New task creation form
│   ├── LogStream.tsx            # Real-time SSE log viewer
│   ├── WorkspaceCard.tsx        # Workspace summary card
│   ├── WorkspaceManager.tsx     # Workspace create/delete UI
│   ├── WorkspaceResources.tsx   # GPU + RAM resource monitor
│   ├── UsageSummary.tsx         # Token/cost usage stats
│   ├── ToBeReviewNotifier.tsx   # Global browser notification for TO_BE_REVIEW tasks
│   └── ui/                      # shadcn/ui primitives (button, card, badge, input, ...)
│
└── lib/
    ├── api.ts                   # Axios API client (taskAPI, workspaceAPI, logAPI, settingsAPI, ...)
    ├── types.ts                 # TypeScript enums and interfaces
    ├── utils.ts                 # cn() helper + parseUTCDate()
    ├── limits.ts                # MAX_PROMPT_CHARS constant
    └── reviewNotificationSettings.ts # localStorage helpers for notification toggle
```

## Key Pages

| Route | Description |
|-------|-------------|
| `/` | Workspace list, entry point |
| `/workspaces` | Manage workspaces (create, delete, SSH config) |
| `/workspaces/[id]/board` | Kanban board for one workspace |
| `/tasks/new` | Create a new task |
| `/tasks/[id]` | Task detail: status, logs, retry/cancel/merge |
| `/tasks/[id]/terminal` | xterm.js terminal (SSH workspaces only) |
| `/settings` | Max parallel setting + review notification toggle |

## Data Flow

- SWR polls `/api/tasks` (3s), `/api/workspaces` (on demand)
- SSE stream: `GET /api/logs/{run_id}/stream` → EventSource
- WebSocket terminal: `ws://.../api/terminal/{workspace_id}`
- Settings: `GET/PUT /api/settings`

## Dev

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```
