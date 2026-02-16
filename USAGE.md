# 快速使用指南

## 1. 首次设置

```bash
# 1. 运行环境设置（仅首次需要）
setup_env.bat

# 2. 测试安装
venv\Scripts\python.exe test_startup.py
```

## 2. 启动服务器

```bash
# 方式1: 使用启动脚本（推荐）
start_server.bat

# 方式2: 手动启动
cd backend
..\venv\Scripts\python.exe main.py
```

服务器启动后访问：
- API文档: http://127.0.0.1:8000/docs
- 健康检查: http://127.0.0.1:8000/health

## 3. 基本使用流程

### 3.1 注册工作区

```bash
# 使用curl (Windows)
curl -X POST "http://127.0.0.1:8000/workspaces" ^
  -H "Content-Type: application/json" ^
  -d "{\"path\": \"d:/WorkSpace/AI/AI-slave\", \"display_name\": \"AI Slave Project\"}"
```

响应示例：
```json
{
  "workspace_id": 1,
  "path": "d:/WorkSpace/AI/AI-slave",
  "display_name": "AI Slave Project",
  "runner_id": 1,
  "concurrency_limit": 1
}
```

### 3.2 创建任务

```bash
# 创建 Claude Code 任务
curl -X POST "http://127.0.0.1:8000/tasks" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\": \"测试任务\", \"prompt\": \"列出当前目录的文件\", \"workspace_id\": 1, \"backend\": \"claude_code\"}"
```

响应示例：
```json
{
  "id": 1,
  "title": "测试任务",
  "prompt": "列出当前目录的文件",
  "workspace_id": 1,
  "backend": "claude_code",
  "status": "TODO",
  "created_at": "2026-02-16T10:00:00",
  "updated_at": "2026-02-16T10:00:00"
}
```

### 3.3 查看任务状态

```bash
# 查看所有任务
curl "http://127.0.0.1:8000/tasks"

# 查看特定任务
curl "http://127.0.0.1:8000/tasks/1"
```

任务状态：
- `TODO`: 待执行
- `RUNNING`: 执行中
- `DONE`: 已完成
- `FAILED`: 失败
- `CANCELLED`: 已取消

### 3.4 查看任务日志

```bash
# 查看任务的运行日志
curl "http://127.0.0.1:8000/logs/runs/1"
```

### 3.5 查看运行器状态

```bash
# 查看所有运行器
curl "http://127.0.0.1:8000/runners"
```

## 4. 常见任务示例

### 使用 Claude Code

```bash
# 示例1: 代码审查
curl -X POST "http://127.0.0.1:8000/tasks" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\": \"代码审查\", \"prompt\": \"审查 backend/main.py 的代码质量\", \"workspace_id\": 1, \"backend\": \"claude_code\"}"

# 示例2: 生成测试
curl -X POST "http://127.0.0.1:8000/tasks" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\": \"生成测试\", \"prompt\": \"为 backend/models.py 生成单元测试\", \"workspace_id\": 1, \"backend\": \"claude_code\"}"
```

### 使用 Codex CLI

```bash
# 示例: 代码生成
curl -X POST "http://127.0.0.1:8000/tasks" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\": \"生成API\", \"prompt\": \"创建一个用户认证的API端点\", \"workspace_id\": 1, \"backend\": \"codex_cli\"}"
```

## 5. 调试技巧

### 5.1 查看服务器日志

服务器日志会输出到控制台，包括：
- 任务调度信息
- 执行状态
- 错误信息

### 5.2 检查数据库

```bash
# 使用 sqlite3 查看数据库
cd backend
sqlite3 tasks.db "SELECT * FROM tasks;"
sqlite3 tasks.db "SELECT * FROM runs;"
```

### 5.3 测试连接

```bash
# 测试API是否可访问
curl http://127.0.0.1:8000/health

# 查看API文档
# 浏览器访问: http://127.0.0.1:8000/docs
```

## 6. 故障排除

### 问题1: 无法启动服务器

```bash
# 检查Python版本
venv\Scripts\python.exe --version
# 应该显示: Python 3.9.13

# 重新安装依赖
cd backend
..\venv\Scripts\pip.exe install -r requirements.txt
```

### 问题2: 数据库错误

```bash
# 删除并重新创建数据库
cd backend
del tasks.db
..\venv\Scripts\python.exe -c "import asyncio; from database import init_db; asyncio.run(init_db())"
```

### 问题3: 编码错误

确保运行脚本时设置了正确的编码：
```bash
set PYTHONIOENCODING=utf-8
```

## 7. 配置说明

编辑 `backend/.env` 文件来覆盖默认配置：

```env
# API配置
API_HOST=127.0.0.1
API_PORT=8000

# 数据库
DATABASE_URL=sqlite+aiosqlite:///./tasks.db

# 调度器
SCHEDULER_INTERVAL=5
HEARTBEAT_INTERVAL=30

# 日志
LOG_LEVEL=INFO
```

## 8. 安全提示

1. 不要在生产环境中使用 `danger-full-access` 沙盒模式
2. 定期备份数据库文件 `backend/tasks.db`
3. 限制API访问（通过防火墙或代理）
4. 审查所有AI生成的代码后再应用到生产环境
