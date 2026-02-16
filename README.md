# AI Task Manager

分布式AI任务调度与管理系统，支持 Claude Code 和 Codex CLI。

## 快速开始

### 1. 环境设置

```bash
# 初次安装（自动创建虚拟环境并安装依赖）
./scripts/setup_env.sh

# 测试安装
./scripts/test.sh
```

### 2. 启动服务器

```bash
./scripts/start_server.sh
```

服务器将启动在 `http://127.0.0.1:8000`

- API 文档: http://127.0.0.1:8000/docs
- 健康检查: http://127.0.0.1:8000/health

## 项目结构

```
AI-slave/
├── backend/              # 后端服务
│   ├── api/             # API 路由层
│   │   ├── tasks.py     # 任务管理接口
│   │   ├── workspaces.py # 工作区管理
│   │   ├── runners.py   # 运行器管理
│   │   └── logs.py      # 日志查看
│   ├── core/            # 核心业务逻辑
│   │   ├── backends/    # AI CLI 适配器
│   │   │   ├── base.py         # 适配器基类
│   │   │   ├── claude_code.py  # Claude Code 适配器
│   │   │   └── codex.py        # Codex CLI 适配器
│   │   ├── executor.py  # 任务执行引擎
│   │   └── scheduler.py # 任务调度器
│   ├── runner/          # 运行器代理
│   │   └── agent.py     # 本地运行器
│   ├── config.py        # 配置管理
│   ├── database.py      # 数据库连接
│   ├── models.py        # SQLAlchemy 模型
│   ├── schemas.py       # Pydantic 数据模式
│   ├── main.py          # 应用入口
│   └── requirements.txt # Python 依赖
├── scripts/             # 工具脚本
│   ├── setup_env.sh     # 环境设置
│   ├── start_server.sh  # 服务器启动
│   └── test.sh          # 测试运行
├── tests/               # 测试代码
│   └── test_startup.py  # 启动测试
├── docs/                # 项目文档
│   ├── tasks/           # 任务计划文档
│   ├── AGENTS.md        # Agent 配置说明
│   ├── CLAUDE.md        # Claude 使用指南
│   ├── usage.md         # 详细使用文档
│   └── log.md           # 开发日志
├── venv/                # Python 虚拟环境
└── README.md            # 项目说明（本文件）
```

## 核心概念

### Task（任务）
一个需要 AI 执行的工作单元，包含 prompt、工作区、后端选择等。

### Workspace（工作区）
代码项目目录的抽象，**同一工作区的任务串行执行**，不同工作区可并行。

### Runner（运行器）
部署在特定环境（本机/远程/容器）的执行节点，负责实际执行任务。

### Backend（后端）
AI CLI 工具的适配器，当前支持：
- `claude_code`: Claude Code CLI
- `codex_cli`: Codex CLI

## API 使用示例

### 注册工作区

```bash
curl -X POST "http://127.0.0.1:8000/workspaces" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "d:/WorkSpace/AI/AI-slave",
    "display_name": "AI Slave Project"
  }'
```

### 创建任务

```bash
curl -X POST "http://127.0.0.1:8000/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "列出文件",
    "prompt": "列出当前目录的所有文件",
    "workspace_id": 1,
    "backend": "claude_code"
  }'
```

### 查看任务列表

```bash
curl "http://127.0.0.1:8000/tasks"
```

### 查看任务日志

```bash
curl "http://127.0.0.1:8000/logs/runs/1"
```

## 配置

项目配置通过环境变量或 `.env` 文件管理。参考 `backend/.env.example`:

```bash
# 复制示例配置
cp backend/.env.example backend/.env

# 编辑配置
vim backend/.env
```

主要配置项：
- `API_HOST`: API 服务器主机（默认: 127.0.0.1）
- `API_PORT`: API 服务器端口（默认: 8000）
- `SCHEDULER_INTERVAL`: 调度器检查间隔（秒）
- `HEARTBEAT_INTERVAL`: 心跳间隔（秒）

## 核心特性

### ✅ 当前已实现 (M1)

- [x] Web API 任务管理
- [x] 按工作区串行调度
- [x] Claude Code 集成
- [x] Codex CLI 集成
- [x] 实时日志查看
- [x] 运行器心跳监控
- [x] 任务状态管理

### 🚧 计划中 (M2+)

- [ ] 任务取消功能（进程终止）
- [ ] 额度监控与告警
- [ ] Web UI 界面
- [ ] 多运行器支持
- [ ] Git worktree 并行化
- [ ] 任务依赖 DAG

## 技术栈

- **Backend**: Python 3.9.13
- **Framework**: FastAPI + SQLAlchemy
- **Database**: SQLite (async)
- **AI Tools**: Claude Code, Codex CLI

## 开发环境要求

- Python 3.9.13
- Windows + Git Bash
- Claude Code CLI (可选)
- Codex CLI (可选)

## 故障排除

### 问题1: 服务器无法启动

```bash
# 检查 Python 版本
./venv/Scripts/python.exe --version

# 重新安装依赖
./scripts/setup_env.sh
```

### 问题2: 编码错误

确保使用 UTF-8 编码：
```bash
export PYTHONIOENCODING=utf-8
```

### 问题3: 数据库错误

```bash
# 删除并重建数据库
rm backend/tasks.db
./scripts/start_server.sh
```

## 文档

- [详细使用指南](docs/usage.md)
- [任务计划文档](docs/tasks/1.md)
- [开发日志](docs/log.md)

## License

Private Project

## 贡献者

- 本项目
