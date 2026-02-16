# AI Task Manager

AI任务管理系统，支持Claude Code和Codex CLI的任务调度和执行。

## 环境要求

- Python 3.9.13
- Windows 环境
- Claude Code CLI 或 Codex CLI

## 快速开始

### 1. 设置环境

首次运行需要创建虚拟环境并安装依赖：

```bash
# 运行环境设置脚本
setup_env.bat
```

该脚本会自动：
- 使用 Python 3.9.13 创建虚拟环境
- 安装所有必需的依赖包

### 2. 启动服务器

```bash
# 运行启动脚本
start_server.bat
```

或者手动启动：

```bash
cd backend
..\venv\Scripts\python.exe main.py
```

服务器将在 `http://127.0.0.1:8000` 启动。

### 3. 测试安装

运行测试脚本验证所有组件正常工作：

```bash
venv\Scripts\python.exe test_startup.py
```

## API 端点

- `GET /` - 根端点，返回API信息
- `GET /health` - 健康检查
- `POST /tasks` - 创建新任务
- `GET /tasks` - 列出所有任务
- `POST /workspaces` - 注册工作区
- `GET /runners` - 查看运行器状态

完整的API文档访问：`http://127.0.0.1:8000/docs`

## 项目结构

```
AI-slave/
├── backend/              # 后端代码
│   ├── api/             # API路由
│   ├── core/            # 核心功能
│   │   ├── backends/    # Claude Code和Codex适配器
│   │   ├── executor.py  # 任务执行器
│   │   └── scheduler.py # 任务调度器
│   ├── runner/          # 运行器代理
│   ├── config.py        # 配置
│   ├── database.py      # 数据库连接
│   ├── models.py        # 数据模型
│   ├── schemas.py       # Pydantic模式
│   └── main.py          # 应用入口
├── venv/                # Python虚拟环境
├── setup_env.bat        # 环境设置脚本
├── start_server.bat     # 服务器启动脚本
└── test_startup.py      # 启动测试脚本
```

## 配置

配置文件位于 `backend/config.py`，主要配置项：

- `api_host`: API服务器主机（默认: 127.0.0.1）
- `api_port`: API服务器端口（默认: 8000）
- `database_url`: 数据库URL（默认: sqlite+aiosqlite:///./tasks.db）
- `scheduler_interval`: 调度器检查间隔（秒）
- `heartbeat_interval`: 心跳间隔（秒）

可以通过创建 `.env` 文件来覆盖默认配置。

## 已修复的兼容性问题

在Python 3.9.13环境下，已修复以下兼容性问题：

1. **SQLAlchemy 1.4.x 兼容性**
   - 使用 `sessionmaker` 代替 `async_sessionmaker`（2.0+特性）
   - 修复了 Task-Run 关系配置

2. **依赖版本更新**
   - sse-starlette: 1.6.2 → 1.6.5
   - aiosqlite: 0.17.0 → 0.19.0

3. **Windows编码支持**
   - 添加UTF-8编码处理，支持Unicode字符输出
   - 防止重复包装stdout/stderr

## 开发备注

- 使用Python 3.9.13（不要使用conda base的3.7）
- 虚拟环境路径：`d:\WorkSpace\AI\AI-slave\venv`
- Python路径：`C:\Users\15225\AppData\Local\Programs\Python\Python39\python.exe`

## 下一步

- [ ] 配置Claude Code和Codex CLI
- [ ] 创建第一个任务
- [ ] 添加前端界面
- [ ] 实现任务取消功能
- [ ] 添加日志查看功能
