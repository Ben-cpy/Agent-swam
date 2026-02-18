# AI Task Manager - Feature Plan

## Project Overview

A web-based task orchestration system that manages AI-powered development tasks via Claude Code and Codex CLI, running in isolated git worktrees. Currently a local-only system with a Kanban-style task board, real-time log streaming, and workspace management.

---

## Planned Features

### 1. Dynamic Model Selection per Task

**Problem**: AI backends (Claude Code, Codex CLI) are hardcoded; models keep being updated and users cannot choose.

**Goal**: Allow users to select the model when creating or running a task. Model lists are fetched dynamically at startup (and on-demand), not hardcoded.

**Requirements**:
- On backend startup, query each configured CLI tool for its available model list
- Cache the model list with a TTL (e.g., 10 minutes), re-fetch on demand
- Expose a `/api/models` endpoint that returns `{backend: "claude_code" | "codex", models: [...]}`
- For Codex: also expose `reasoning_effort` levels (`low | medium | high`) as these are model-level settings
- Task creation form: add a model selector dropdown populated from the API, defaulting to the provider's recommended model
- Store the selected model + reasoning_effort in the `Task` record
- Pass the model flag to the CLI adapter at execution time

**Implementation notes**:
- `claude code models` or parse `claude --version` output; fall back to known list if CLI unavailable
- Codex: `openai models list` filtered by capability, or use the OpenAI API directly
- Frontend: SWR fetch on form open; show a loading skeleton if models haven't loaded yet

---

### 2. Usage / Quota Data (Fix "Failed to load usage data")

**Problem**: The usage page was removed in M3, and there is currently no way to see token consumption or remaining quota. Claude Code only exposes usage inside an interactive session via `/status`.

**Root Cause Analysis**:
- Claude Code does not expose usage via a machine-readable file or API; it is only available interactively
- The previous usage API endpoint likely tried to scrape a file or call a non-existent API and failed silently
- Codex similarly has no CLI flag to dump remaining quota

**Goal**: Surface useful usage data within the constraints of each tool.

**Approach A — Parse execution output (short-term)**:
- Both adapters already parse token counts from JSONL/stream-json output
- Aggregate per-task token + cost data that is already stored in `Run` records
- Add a `/api/usage` endpoint that queries `Run` table and returns total tokens, estimated cost, and per-workspace breakdown
- Display this in the frontend as a simple summary card on the dashboard

**Approach B — Interactive shell probe (medium-term)**:
- Spawn a short-lived Claude Code interactive session, send `/status`, capture the output, then exit
- Parse the structured output for quota/balance information
- This is fragile and depends on output format stability; use only as a supplement to Approach A
- Cache the result for 5 minutes to avoid excessive spawning

**Note**: True remaining-quota data from Anthropic requires using the Anthropic Console API (if available for the account type). Consider linking directly to the Console URL as a fallback.

---

### 3. Web SSH Terminal with tmux Session Persistence

**Goal**: Each task corresponds to a persistent terminal session. Users can open a browser tab, interact with the running task's shell in real time, interrupt it, and return later to see the full history — all without SSH clients.

**Architecture**:

```
Browser (xterm.js)
    ↕  WebSocket
Backend WebSocket Gateway (FastAPI)
    ↕  SSH (paramiko / asyncssh)
Remote Host
    └── tmux session  ←→  AI task process
```

**Components**:

#### 3a. tmux Session Naming Convention
- Each task maps to a tmux session named `aitask-{task_id}`
- On task start, the executor creates the tmux session and runs the AI CLI inside it
- On task completion/cancellation, the session is kept alive for inspection (cleaned up manually or by TTL)

#### 3b. Backend WebSocket Gateway
- New endpoint: `ws://.../api/tasks/{id}/terminal`
- On connect: SSH into the workspace host, attach to (or create) the `aitask-{task_id}` tmux session
- Bidirectional relay: browser keystrokes → tmux stdin; tmux stdout → browser
- Handle resize events (PTY resize via `SIGWINCH`)
- Library candidates: `asyncssh` (pure async Python, preferred) or `paramiko` + threads
- For local workspaces: use a subprocess PTY instead of SSH (no SSH needed for localhost)

#### 3c. Frontend Terminal UI
- Library: `xterm.js` + `xterm-addon-fit` for responsive sizing
- New page: `/tasks/[id]/terminal`
- Connects via WebSocket on mount, disconnects cleanly on unmount
- Preserves scrollback from tmux's history buffer (send `tmux capture-pane` snapshot on attach)
- Toolbar: disconnect button, resize hint, session name display
- Task detail page: add "Open Terminal" button that opens the terminal page

#### 3d. Multi-Session Management UI
- Sidebar or tab bar showing all active terminal sessions
- Clicking a session navigates to its terminal page
- Shows task name, status badge, and last-active timestamp
- Sessions survive page refresh (backed by tmux on the server)

#### 3e. Task Execution Integration
- Modify `executor.py`: when workspace type is `local`, wrap the AI CLI call in `tmux new-session -d -s aitask-{id} -- <command>`
- For SSH workspaces: SSH in, then run the tmux command on the remote host
- Store the tmux session name in the `Run` record
- On cancellation: send `tmux kill-session -t aitask-{id}` instead of killing the subprocess directly

**Dependencies to add**:
- Backend: `asyncssh`, `websockets` (or use FastAPI's built-in WebSocket support)
- Frontend: `xterm`, `xterm-addon-fit`, `xterm-addon-web-links`

---

## Implementation Order

1. **Dynamic Model Selection** — self-contained, no infrastructure changes, high user value
2. **Usage Data (Approach A)** — re-use existing `Run` data, low risk, fixes the broken page
3. **tmux + WebSocket Terminal** — largest scope; build in sub-steps:
   - 3a: tmux integration in executor (local only)
   - 3b: WebSocket gateway (local PTY first, then SSH)
   - 3c: xterm.js frontend terminal page
   - 3d: multi-session sidebar

---

## Open Questions

- For model fetching: should the list be fetched at backend startup only, or also callable from the frontend on demand?
A:  at backend startup only
- For Codex `reasoning_effort`: is this per-model or a global setting? Needs verification against current Codex CLI docs.
A: you should search web and use codex-cli to get info 
- For the terminal: should tmux sessions be auto-cleaned after task DONE/FAILED, or always kept until manual deletion? Suggest: keep for 24h, then auto-purge.
A: aways keep it for a workspace,
- For SSH workspaces: `asyncssh` requires SSH credentials stored per workspace. The current `Workspace` model has `ssh_host`/`ssh_user` fields — are keys stored or does it use the system agent?
A: for ssh, I am in windows, I use ssh config to just like 'ssh cloud' to connect to a server, 
- Windows compatibility: tmux is not native on Windows. For local workspaces on Windows, use ConPTY or WSL as the PTY layer instead.
A: I mean tmux runs on the linux server, I dont need these in windows local, this is just for remote workspace 

And i want to use the git worktree to develop them and run them parallel, and finaly merge them all into my branch main.