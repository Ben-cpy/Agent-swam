# task info


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


# requirement
+ 目前是windows环境, 使用的是git bash 作为终端
+ 可以通过命令行启动claude 和 codex
+ 多联网确认下 claude code 和 codex  的文档, 传入相关参数, 你也可以使用 -h 参数来确认可用参数
+ 思考和编程时使用英文, 回答问题时,使用中文回答
+ ~\AppData\Local\Programs\Python\Python39\python.exe 这个是我python 路径
+ 执行任务过程, 遇到问题,或者完成关键内容, 向log.md 中记录, 格式为一行简短的描述
+ 不要生成非常多混乱的文档, 每当你完成任务/debug 完成问题之后, 你只需要给我一个最终文档md即可
+ 生成计划时,plan md 直接生成在当前目录下, 而不是.claude\plans\xx.md
+ 我有两个人格, 一个是产品经理人格, 主要关注一些宏观的可观测性指标, 大部分情况, 我都是这个状态,我只需要关注一些结果, 过程的细节我并不关注, 只负责控制一些大的框架流程, 关注它实现了什么功能, 输入输出是什么,整体流程大致是如何. 另外一个人格是工程师人格, 涉及到一些重要性能调优或者是关键行为, 需要我来讨论一些代码的细节.
+ 当你创建git worktree 进行工作时, 完成修改的标志是, 你在这个工作区里面完成了对应的内容commit(涉及到的内容应该简洁,冗余文件不需要提交到commit中), 不要让我手动帮你提交commit
# 经验教训沉淀

每次遇到问题或完成重要改动后，要在 [PROGRESS.md](./PROGRESS.md) 中记录：

- 遇到了什么问题
- 如何解决的
- 以后如何避免
- **必须附上 git commit ID**

**同样的问题不要犯两次！**

# 冲突处理

**Rebase 失败时的处理流程：**

1. 如果是 “unstaged changes” 错误，先 commit 或 stash 当前改动
2. 如果有 merge conflicts：

   * 查看冲突文件：`git status`
   * 读取冲突文件内容，理解双方改动意图
   * 手动解决冲突（保留正确的代码）
   * `git add <resolved-files>`
   * `git rebase --continue`
3. 重复直到 rebase 完成

---

**测试失败时的处理流程：**

1. 运行测试：`npm test`
2. 如果失败，分析错误信息
3. 修复代码中的 bug
4. 重新运行测试，直到全部通过
5. 提交修复：`git commit -m "fix: ..."`

---

**不要放弃：**

遇到 rebase 或测试失败时，必须解决问题后才能继续，不能直接跳过错误。
