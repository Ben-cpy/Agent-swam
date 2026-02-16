# AI 任务管理器本地实现计划 (M1 - 最小闭环)

## 实现目标

基于 tasks/1.md 的规划,实现 M1 里程碑:本地 Windows 环境下的最小可用版本,支持 Claude Code 和 Codex CLI 两个后端。

## 技术栈

- **后端**: Python 3.10+ + FastAPI + SQLite
- **前端**: Next.js 14 + React 18 + TypeScript + Tailwind CSS
- **通信**: REST API + SSE (Server-Sent Events)
- **AI 后端**: Claude Code CLI + Codex CLI

## 项目结构

```
AI-slave/
├── backend/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理
│   ├── database.py             # SQLite 连接和初始化
│   ├── models.py               # SQLAlchemy 模型
│   ├── schemas.py              # Pydantic 数据模型
│   ├── api/
│   │   ├── tasks.py            # 任务 API
│   │   ├── runners.py          # Runner API
│   │   ├── workspaces.py       # Workspace API
│   │   └── logs.py             # 日志流 API (SSE)
│   ├── core/
│   │   ├── scheduler.py        # 任务调度器
│   │   ├── executor.py         # 任务执行逻辑
│   │   └── backends/
│   │       ├── base.py         # 后端抽象基类
│   │       ├── claude_code.py  # Claude Code 适配器
│   │       └── codex.py        # Codex CLI 适配器
│   ├── runner/
│   │   └── agent.py            # Runner 进程 (本地模式)
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx        # 看板主页
│   │   │   ├── tasks/
│   │   │   │   ├── new/page.tsx     # 新建任务
│   │   │   │   └── [id]/page.tsx    # 任务详情
│   │   │   └── runners/page.tsx     # Runner 管理
│   │   ├── components/
│   │   │   ├── TaskBoard.tsx        # 看板组件
│   │   │   ├── TaskCard.tsx         # 任务卡片
│   │   │   ├── TaskForm.tsx         # 任务表单
│   │   │   ├── LogStream.tsx        # 实时日志
│   │   │   └── RunnerStatus.tsx     # Runner 状态
│   │   ├── hooks/
│   │   │   ├── useSSE.ts            # SSE 钩子
│   │   │   └── useAPI.ts            # API 请求钩子
│   │   └── types/
│   │       └── api.ts               # API 类型定义
│   └── public/
└── README.md
```

## 核心实现步骤

### 第一阶段: 后端基础设施 (P0)

#### 1. 数据库模型 (backend/models.py)

```python
# M1 阶段简化版,只实现必要表

class Task(Base):
    id: int (PK)
    title: str
    prompt: str
    workspace_id: int (FK)
    backend: enum ['claude_code', 'codex_cli']
    status: enum ['TODO', 'RUNNING', 'DONE', 'FAILED', 'CANCELLED']
    created_at: datetime
    updated_at: datetime
    run_id: int (FK, nullable)

class Workspace(Base):
    workspace_id: int (PK)
    path: str (absolute path)
    display_name: str
    runner_id: int (FK)
    # M1: 固定 concurrency_limit=1

class Runner(Base):
    runner_id: int (PK)
    env: str (例如 'local-windows')
    capabilities: json (["claude_code", "codex_cli"])
    heartbeat_at: datetime
    status: enum ['ONLINE', 'OFFLINE']
    # M1: max_parallel=1

class Run(Base):
    run_id: int (PK)
    task_id: int (FK)
    runner_id: int (FK)
    backend: str
    started_at: datetime
    ended_at: datetime (nullable)
    exit_code: int (nullable)
    error_class: enum ['CODE', 'TOOL', 'NETWORK', 'UNKNOWN'] (nullable)
    log_blob: text (M1 直接存文本)
    # M1: 暂不实现 usage_json
```

#### 2. Backend 适配器实现

**Claude Code 适配器** (backend/core/backends/claude_code.py):
- 使用 `claude -p --output-format stream-json --dangerously-skip-permissions <prompt>`
- 解析 stream-json 输出,提取事件和日志
- 捕获 exit code
- 错误分类: 网络错误、工具调用错误等

**Codex 适配器** (backend/core/backends/codex.py):
- 使用 `codex exec --json --sandbox danger-full-access "<prompt>"`
- 解析 JSONL 事件流 (turn.started, turn.completed, etc.)
- 提取日志和状态
- M1 阶段先不提取 usage (留待 M3)

#### 3. 任务调度器 (backend/core/scheduler.py)

```python
# M1 简化版调度逻辑
def schedule_tick():
    # 1. 找到 status=TODO 的任务,按创建时间排序
    # 2. 对每个任务:
    #    - 检查 workspace 是否已有 RUNNING 任务 (串行约束)
    #    - 检查对应 runner 是否 ONLINE
    # 3. 选择可执行的第一个任务
    # 4. 创建 Run 记录,设置 task.status=RUNNING
    # 5. 调用 runner 执行 (本地模式直接调用)

# M1: 暂不实现 lease 机制,任务一旦 RUNNING 直到完成
```

#### 4. FastAPI 接口

**核心 API**:
- POST /api/tasks - 创建任务
- GET /api/tasks - 列出任务 (支持按 status 筛选)
- GET /api/tasks/{id} - 获取任务详情
- POST /api/tasks/{id}/cancel - 取消任务
- GET /api/workspaces - 列出 workspaces
- POST /api/workspaces - 创建 workspace
- GET /api/runners - 列出 runners
- GET /api/logs/{run_id}/stream - SSE 实时日志流

### 第二阶段: Runner 实现 (P0)

#### Runner 本地模式 (backend/runner/agent.py)

M1 阶段 runner 与 controller 同进程运行:
- 启动时自动注册本地 runner
- 心跳更新 (每 30 秒)
- 接收调度器派发的任务
- 在指定 workspace 目录执行 CLI 命令
- 流式捕获 stdout/stderr
- 上报执行结果和日志

执行流程:
```python
async def execute_task(task, workspace):
    backend = get_backend(task.backend)  # claude_code 或 codex

    # 1. 切换到 workspace 目录
    os.chdir(workspace.path)

    # 2. 构造命令
    cmd = backend.build_command(task.prompt)

    # 3. 流式执行
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=PIPE,
        stderr=STDOUT,
        cwd=workspace.path
    )

    # 4. 读取并存储日志
    log_lines = []
    async for line in process.stdout:
        log_lines.append(line.decode())
        # 实时写入数据库或缓存供 SSE 读取

    # 5. 等待完成
    exit_code = await process.wait()

    # 6. 更新 run 和 task 状态
    update_run(run_id, exit_code, log_lines)
    update_task(task_id, 'DONE' if exit_code == 0 else 'FAILED')
```

### 第三阶段: 前端界面 (P0)

#### 1. 主看板页面 (src/app/page.tsx)

布局:
- 顶部导航栏: 项目标题 + 新建任务按钮 + Runner 状态入口
- 看板视图: 5 列 (TODO / RUNNING / DONE / FAILED / CANCELLED)
- 每列显示任务卡片,可拖拽排序 (M1 可选功能)

任务卡片内容:
- 标题
- Workspace 名称
- Backend 图标
- 创建时间
- 点击进入详情页

API 交互:
- 使用 SWR 或 React Query 定期轮询 /api/tasks
- 轮询间隔: 2 秒

#### 2. 新建任务页面 (src/app/tasks/new/page.tsx)

表单字段:
- 标题 (text input)
- Prompt (textarea, 多行)
- Workspace (select dropdown)
- Backend (radio: Claude Code / Codex CLI)

提交后跳转回主看板

#### 3. 任务详情页面 (src/app/tasks/[id]/page.tsx)

显示内容:
- 任务基本信息 (标题、workspace、backend、状态、时间)
- 操作按钮: 取消 (仅 TODO/RUNNING 可用)、重试 (FAILED 可用)
- 实时日志流:
  - 使用 EventSource 连接 /api/logs/{run_id}/stream
  - 自动滚动到底部
  - 颜色区分不同日志级别

#### 4. Runner 管理页面 (src/app/runners/page.tsx)

显示内容:
- Runner 列表 (M1 只有一个本地 runner)
- 每个 runner 的状态:
  - 名称/环境
  - 在线状态 (心跳时间)
  - 支持的 backends
  - 当前执行的任务

### 第四阶段: 集成与测试

#### 启动脚本

**后端启动** (backend/main.py):
```python
# 1. 初始化数据库
# 2. 自动注册本地 runner
# 3. 启动调度器 (asyncio background task)
# 4. 启动 FastAPI server (uvicorn)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
```

**前端启动**:
```bash
cd frontend
npm run dev  # 启动 Next.js dev server on port 3000
```

#### 开发工作流

1. 启动后端: `cd backend && python main.py`
2. 启动前端: `cd frontend && npm run dev`
3. 浏览器访问: http://localhost:3000

## 标准化验收方案

### 验收环境准备

#### 前置条件

1. **安装依赖**
   ```bash
   # 后端依赖
   cd backend
   pip install -r requirements.txt

   # 前端依赖
   cd frontend
   npm install
   ```

2. **配置 AI 后端**
   - 确保 Claude Code 已登录: `claude --version` 可用
   - 确保 Codex CLI 已登录: `codex --version` 可用

3. **准备测试 Workspace**
   - 在本地创建一个测试项目目录,例如: `D:\test-workspace-1`
   - 可选: 再创建第二个测试目录 `D:\test-workspace-2` (用于验证多 workspace 场景)

4. **配置 Workspace**
   - 启动系统后,在 Web UI 中添加 workspace
   - 或通过 API 直接创建:
     ```bash
     curl -X POST http://localhost:8000/api/workspaces \
       -H "Content-Type: application/json" \
       -d '{"path": "D:\\test-workspace-1", "display_name": "测试项目1"}'
     ```

### 验收测试套件

#### 测试 1: 系统启动与健康检查

**步骤**:
1. 启动后端服务: `cd backend && python main.py`
2. 确认输出包含:
   - "Database initialized"
   - "Local runner registered"
   - "Scheduler started"
   - "Uvicorn running on http://127.0.0.1:8000"
3. 启动前端: `cd frontend && npm run dev`
4. 浏览器访问 http://localhost:3000

**预期结果**:
- ✅ 看板页面正常显示,包含 5 个状态列
- ✅ 顶部导航栏显示正常
- ✅ 点击 "Runner" 页面,看到本地 runner 状态为 ONLINE
- ✅ Runner 显示支持 claude_code 和 codex_cli

---

#### 测试 2: 创建任务并执行 (Claude Code)

**步骤**:
1. 点击 "新建任务" 按钮
2. 填写表单:
   - 标题: "测试任务 - 读取文件"
   - Prompt: "Read the README.md file and tell me what this project is about"
   - Workspace: 选择 "测试项目1"
   - Backend: 选择 "Claude Code"
3. 点击提交
4. 返回看板页面

**预期结果**:
- ✅ 任务出现在 TODO 列
- ✅ 2-5 秒内任务自动移动到 RUNNING 列
- ✅ 点击任务卡片进入详情页
- ✅ 详情页显示实时日志流
- ✅ 可以看到 Claude Code 的输出
- ✅ 任务完成后自动移动到 DONE 或 FAILED 列
- ✅ 详情页显示完整日志和 exit code

**验收标准**:
- 整个流程无需任何命令行操作
- 日志实时更新,无需刷新页面
- 任务状态自动流转

---

#### 测试 3: 创建任务并执行 (Codex CLI)

**步骤**:
1. 创建新任务:
   - 标题: "测试任务 - Codex 写文件"
   - Prompt: "Create a hello.txt file with content 'Hello from Codex'"
   - Workspace: 选择 "测试项目1"
   - Backend: 选择 "Codex CLI"
2. 观察执行过程

**预期结果**:
- ✅ 任务正常执行
- ✅ 日志显示 Codex 的 JSONL 事件流
- ✅ 完成后在 workspace 目录看到 hello.txt 文件
- ✅ 文件内容正确

---

#### 测试 4: 同 Workspace 串行约束

**步骤**:
1. 快速创建 3 个任务,全部使用 "测试项目1",backend 随意:
   - 任务 A: "List all files in the current directory"
   - 任务 B: "Create a file called test1.txt"
   - 任务 C: "Create a file called test2.txt"
2. 观察看板

**预期结果**:
- ✅ 任务 A 开始执行,任务 B、C 保持在 TODO
- ✅ 任务 A 完成后,任务 B 自动开始
- ✅ 任务 B 完成后,任务 C 自动开始
- ✅ **严格串行,同一时刻只有一个任务在 RUNNING 状态**

**验收标准**:
- 在任务执行过程中,不断刷新看板,确认同 workspace 永远只有 1 个 RUNNING

---

#### 测试 5: 不同 Workspace 并行执行 (可选)

**前提**: 已配置第二个 workspace "测试项目2"

**步骤**:
1. 创建任务 A: workspace="测试项目1", 长耗时 prompt (例如 "Write a long essay about AI")
2. 创建任务 B: workspace="测试项目2", 快速 prompt (例如 "Echo hello")
3. 观察看板

**预期结果**:
- ✅ 任务 A 和任务 B 可以同时处于 RUNNING 状态
- ✅ 两个任务互不阻塞

**注**: M1 阶段因为 runner max_parallel=1,可能无法真正并行。此测试用于验证调度器逻辑正确,实际并行在 M2 实现。

---

#### 测试 6: 任务取消功能

**步骤**:
1. 创建一个长耗时任务 (例如 "Write a detailed analysis of quantum computing")
2. 进入任务详情页
3. 点击 "取消" 按钮

**预期结果**:
- ✅ 任务状态变为 CANCELLED
- ✅ 后台进程被终止 (在 task manager 中看不到 claude/codex 进程)
- ✅ 日志显示取消时间

---

#### 测试 7: 错误处理

**步骤**:
1. 创建一个故意失败的任务:
   - Prompt: "Delete all files in the system" (Claude/Codex 应拒绝)
   - 或: 在不存在的 workspace 路径执行任务

**预期结果**:
- ✅ 任务状态变为 FAILED
- ✅ 详情页显示错误日志
- ✅ Run 记录中 error_class 正确分类 (TOOL / CODE / NETWORK)
- ✅ 可以点击 "重试" 按钮重新执行

---

#### 测试 8: Runner 心跳与离线检测

**步骤**:
1. 在 Runner 页面查看 runner 状态
2. 强制终止后端进程 (Ctrl+C)
3. 等待 30-60 秒
4. 重启后端

**预期结果**:
- ✅ 终止后 runner 状态变为 OFFLINE (前端轮询检测)
- ✅ 重启后自动恢复 ONLINE
- ✅ 未完成的任务保持在原状态 (M1 无自动恢复,M2 有 lease 机制)

---

#### 测试 9: 日志流稳定性

**步骤**:
1. 创建一个会产生大量输出的任务 (例如 "List all npm packages globally installed")
2. 在详情页观察日志流

**预期结果**:
- ✅ 日志实时更新,无丢失
- ✅ 自动滚动到底部
- ✅ 长日志不会导致页面卡顿
- ✅ 刷新页面后可以重新加载历史日志

---

### 验收检查清单

#### 功能完整性

- [ ] 创建任务 (Web UI)
- [ ] 任务看板显示 (5 种状态)
- [ ] 任务详情页
- [ ] 实时日志流 (SSE)
- [ ] 任务取消
- [ ] 同 workspace 串行约束
- [ ] Claude Code backend 执行
- [ ] Codex CLI backend 执行
- [ ] Runner 状态监控
- [ ] 错误处理与分类

#### 非功能性

- [ ] 页面响应速度 < 1 秒
- [ ] 日志流延迟 < 500ms
- [ ] 任务调度延迟 < 5 秒
- [ ] 无内存泄漏 (长时间运行)
- [ ] 数据库文件正常生成 (backend/tasks.db)

#### 边界情况

- [ ] 无 workspace 时的提示
- [ ] 空 prompt 的验证
- [ ] 超长日志的处理 (>10MB)
- [ ] 并发创建多个任务
- [ ] 后端崩溃后的恢复

---

### 验收报告模板

```markdown
## AI 任务管理器 M1 验收报告

**验收日期**: YYYY-MM-DD
**验收人**:
**版本**: M1

### 环境信息
- 操作系统: Windows 11
- Python 版本:
- Node.js 版本:
- Claude Code 版本:
- Codex CLI 版本:

### 测试结果总览
- 总测试用例: 9
- 通过: X
- 失败: Y
- 阻塞: Z

### 详细结果

#### ✅ 测试 1: 系统启动与健康检查
- 状态: 通过
- 备注:

#### ✅ 测试 2: 创建任务并执行 (Claude Code)
- 状态: 通过
- 备注:

...

### 遗留问题
1. [问题描述]
2. [问题描述]

### 验收结论
- [ ] 通过,可以投入使用
- [ ] 有小问题,但不阻塞使用
- [ ] 有重大问题,需要修复
```

---

## 后续扩展建议 (M2/M3)

当你验证 M1 可用后,可以考虑:

### M2 扩展
- Lease 机制 (防止 runner 崩溃卡死)
- 多 runner 并行 (max_parallel > 1)
- 任务优先级
- 任务依赖关系

### M3 扩展
- 额度监控 (解析 usage 字段)
- 额度耗尽检测与停机
- 使用量趋势图表
- 账户维度聚合

### 远程部署 (P2)
- Docker 容器化
- Runner 独立部署包
- SSH 远程管理
- 认证与权限

---

## 关键文件清单

### 后端必须实现的文件
1. `backend/main.py` - FastAPI 应用入口
2. `backend/database.py` - 数据库初始化
3. `backend/models.py` - ORM 模型
4. `backend/schemas.py` - API 数据模型
5. `backend/core/scheduler.py` - 任务调度器
6. `backend/core/backends/claude_code.py` - Claude Code 适配
7. `backend/core/backends/codex.py` - Codex CLI 适配
8. `backend/runner/agent.py` - 本地 Runner
9. `backend/api/tasks.py` - 任务 API
10. `backend/api/logs.py` - 日志流 API

### 前端必须实现的文件
1. `frontend/src/app/page.tsx` - 看板主页
2. `frontend/src/app/tasks/new/page.tsx` - 新建任务
3. `frontend/src/app/tasks/[id]/page.tsx` - 任务详情
4. `frontend/src/app/runners/page.tsx` - Runner 管理
5. `frontend/src/components/TaskBoard.tsx` - 看板组件
6. `frontend/src/components/LogStream.tsx` - 日志流组件
7. `frontend/src/hooks/useSSE.ts` - SSE 数据钩子

---

## 时间估算 (仅供参考,不作为承诺)

- 后端开发: 40-60 小时
  - 数据库与模型: 6-8h
  - Backend 适配器: 10-15h
  - 调度器与 Runner: 12-18h
  - API 实现: 8-12h
  - 测试与调试: 4-7h

- 前端开发: 25-35 小时
  - 项目搭建与配置: 3-4h
  - 看板页面: 6-8h
  - 任务详情与日志流: 8-10h
  - 表单与交互: 5-7h
  - 样式优化: 3-6h

- 集成测试: 5-10 小时

**总计**: 70-105 小时 (约 9-14 个工作日)

---

## 注意事项

1. **路径处理**: Windows 路径使用 `\\` 或 `/`,确保跨平台兼容
2. **进程管理**: 使用 asyncio 的 subprocess,避免阻塞
3. **日志存储**: M1 直接存文本,但要考虑日志大小限制 (>10MB 截断)
4. **错误恢复**: M1 不做自动重试,失败任务需手动重试
5. **安全性**: M1 无认证,仅本地使用;M2 再加认证
6. **数据库迁移**: 使用 Alembic 管理 schema 变更 (可选)
