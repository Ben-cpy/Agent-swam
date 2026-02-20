# AI-Slave

一个可视化的 AI 编程任务调度平台。你只需填写任务描述，它会自动调用 Claude Code 或 OpenAI Codex 帮你完成编码工作，并在看板上实时展示进度。

---

## 效果预览

打开 `http://localhost:3000`，你会看到一个类似 Trello 的任务看板：

```
[ TODO ]  →  [ RUNNING ]  →  [ DONE / FAILED ]
```

在这里创建任务 → AI 自动执行 → 查看结果和日志。

---

## 前置要求

在开始之前，请确认你已安装以下工具：

| 工具 | 说明 | 检查命令 |
|------|------|----------|
| Git Bash | Windows 终端（必须） | 打开 Git Bash 即可 |
| Python 3.9 | 后端运行环境 | `python --version` |
| Node.js 18+ | 前端运行环境 | `node --version` |
| Claude Code | AI 执行器 | `claude --version` |

> **Claude Code 还没装？** 参考 [官方文档](https://docs.anthropic.com/claude-code) 安装并登录。

---

## 快速启动（3步）

用 **Git Bash** 打开项目目录，按顺序执行：

### 第 1 步：初始化环境（只需执行一次）

```bash
./scripts/setup_env.sh
```

这会自动创建 Python 虚拟环境并安装依赖，等待完成即可。

---

### 第 2 步：启动后端

**新开一个 Git Bash 窗口**，执行：

```bash
./scripts/start_server.sh
```

看到类似下面的输出说明启动成功：

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

### 第 3 步：启动前端

**再新开一个 Git Bash 窗口**，执行：

```bash
cd frontend
npm install    # 第一次需要，之后可跳过
npm run dev
```

看到下面的输出说明启动成功：

```
▲ Next.js ready on http://localhost:3000
```

---

## 开始使用

浏览器打开 **http://localhost:3000**

### 创建第一个任务

1. 点击右上角 **「+ 新建任务」**
2. 填写任务描述，例如：`写一个读取 CSV 文件并统计行数的 Python 脚本`
3. 选择工作区（默认选本地即可）
4. 点击 **「提交」**

任务会自动进入队列，AI 开始执行后状态变为 `RUNNING`，完成后变为 `DONE`。

### 查看执行日志

点击任务卡片，可以看到 AI 执行过程的实时日志，包括它写了什么代码、有没有报错等。

---

## 配置 AI 执行器

默认使用 Claude Code。如需切换模型或添加 OpenAI Codex，编辑后端配置：

```bash
cp backend/.env.example backend/.env
```

打开 `backend/.env`，常用配置项：

```ini
# 最大并行任务数（默认 1，新手建议保持）
MAX_PARALLEL=1

# 日志级别（DEBUG 可以看更多细节）
LOG_LEVEL=INFO
```

修改后重启后端生效。

---

## 验证是否正常运行

```bash
curl http://127.0.0.1:8000/health
```

返回 `{"status":"healthy"}` 说明后端正常。

---

## 常见问题

**Q: 启动后端报错 `ModuleNotFoundError`？**
> 重新运行 `./scripts/setup_env.sh`，确保虚拟环境创建成功。

**Q: 前端打开是空白页？**
> 确认后端已启动，并检查 `frontend/.env.local` 中 `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`。

**Q: 任务一直卡在 RUNNING？**
> 检查 Claude Code 是否已登录：在 Git Bash 中运行 `claude --version`，然后运行 `claude` 确认可以正常使用。

**Q: 想清空数据重新开始？**
> ```bash
> ./scripts/clean_workspace.sh
> ```

---

## 目录结构（简版）

```
AI-slave/
├── backend/          # Python 后端（FastAPI）
├── frontend/         # 前端界面（Next.js）
├── scripts/          # 启动/清理脚本
└── tasks/            # 任务工作区（自动生成）
```

---

## 技术栈

- **后端**：Python + FastAPI
- **前端**：Next.js + React + Tailwind CSS
- **AI 执行器**：Claude Code / OpenAI Codex
- **数据库**：SQLite（无需额外安装）
