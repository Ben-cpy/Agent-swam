# AI-Slave Requirements

## Implemented

- Kanban board (TODO / RUNNING / DONE / FAILED) with real-time SWR polling
- Task creation with title, prompt, model, permission mode, workspace selection
- Per-task git worktree isolation (auto branch `task-{id}`, cleanup on delete)
- Cancel / retry / continue tasks
- Claude Code adapter: stream-json output, usage tracking, quota detection
- OpenAI Codex adapter: JSONL output, usage tracking
- Model selection per task (Claude models + Codex o3/o4-mini)
- Claude permission modes (plan, bypassPermissions, acceptEdits, etc.)
- Local workspace support (filesystem path)
- SSH workspace support (remote host + directory)
- SSH container workspace support (Docker containers via SSH)
- Serial execution per workspace (1 task at a time)
- Real-time log streaming via SSE with auto-reconnect
- GPU + RAM resource monitoring (nvidia-smi / wmic / free)
- Usage aggregation dashboard (cost + tokens)
- WebSocket terminal access for SSH tasks (xterm.js + tmux)
- Runner heartbeat registration (local runner auto-registers on startup)

## Planned / Not Implemented

- Parallel task execution via git worktrees (multiple tasks concurrently per workspace)
- GPU resource conflict detection across workspaces sharing the same server
- Task auto-splitting: break a large task into parallel subtasks
- Context summarization / pruning to prevent agent context bloat
- Proper DB migration system (currently manual ALTER TABLE)
- Authentication / API key protection
- Pagination + virtual scroll for long task/log lists
- Structured logging + monitoring / alerting
