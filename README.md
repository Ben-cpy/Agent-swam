# AI Task Manager

这个版本只保留最关键内容：怎么启动、怎么运行、怎么清理。

## 1) 一次性环境准备

在项目根目录执行（Git Bash）：

```bash
./scripts/setup_env.sh
```

说明：
- 会创建 `venv/`
- 会安装 `backend/requirements.txt`

## 2) 启动后端

终端 A（Git Bash）：

```bash
./scripts/start_server.sh
```

启动成功后：
- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## 3) 启动前端

终端 B（Git Bash）：

```bash
cd frontend
npm install
npm run dev
```

启动成功后：
- Web UI: `http://localhost:3000`

## 4) 最小运行检查

先检查后端：

```bash
curl http://127.0.0.1:8000/health
```

预期返回：

```json
{"status":"healthy"}
```

然后打开：
- `http://localhost:3000`

## 5) 常用命令

```bash
# 后端启动自检
./venv/Scripts/python.exe tests/test_startup.py

# 修复验证（1-6 问题）
./venv/Scripts/python.exe tests/verify_m1_fixes.py

# 前端检查
cd frontend && npm run lint && npm run build
```

## 6) 清理无关内容

可以删除，推荐先删运行产物（不会影响代码）：

```bash
./scripts/clean_workspace.sh
```

会清理：
- `*.log`
- `tasks.db`、`backend/tasks.db`
- `frontend/.next`
- Python `__pycache__`、`.pytest_cache`

如果你想连开发文档也删（会改 git 跟踪文件），可执行：

```bash
./scripts/clean_workspace.sh --deep
```

`--deep` 会额外删除：
- `docs/`
- `tasks/`

## 7) 项目最小保留目录

只保留这些就能跑：
- `backend/`
- `frontend/`
- `scripts/`
- `tests/`
- `venv/`（或你自己的虚拟环境）
- `README.md`

