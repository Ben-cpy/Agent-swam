# Frontend Architecture

AI Task Manager 前端采用 Next.js 14 (App Router) + TypeScript + Tailwind CSS 构建。

## 技术栈

### 核心框架
- **Next.js 16.1.6**: React 框架，使用 App Router
- **React 19**: UI 库
- **TypeScript**: 类型安全

### UI 与样式
- **Tailwind CSS v4**: 实用优先的 CSS 框架
- **shadcn/ui**: 高质量组件库
- **date-fns**: 日期格式化

### 数据管理
- **SWR**: 数据获取和缓存
  - 自动重新验证
  - 3 秒自动刷新
  - 焦点重新验证
- **Axios**: HTTP 客户端

## 项目结构

```
frontend/
├── app/                    # Next.js App Router 页面
│   ├── page.tsx           # 主页 - 任务看板
│   ├── layout.tsx         # 根布局（含 Navbar）
│   ├── tasks/
│   │   ├── new/page.tsx   # 新建任务页面
│   │   └── [id]/page.tsx  # 任务详情页面（动态路由）
│   └── runners/page.tsx   # Runner 管理页面
│
├── components/            # React 组件
│   ├── Navbar.tsx        # 顶部导航栏
│   ├── TaskBoard.tsx     # 5 列任务看板
│   ├── TaskCard.tsx      # 单个任务卡片
│   ├── TaskForm.tsx      # 任务创建表单
│   ├── LogStream.tsx     # 实时日志流（SSE）
│   ├── RunnerCard.tsx    # Runner 信息卡片
│   └── ui/               # shadcn/ui 基础组件
│       ├── button.tsx
│       ├── card.tsx
│       ├── badge.tsx
│       ├── input.tsx
│       ├── textarea.tsx
│       ├── select.tsx
│       └── label.tsx
│
├── lib/                  # 工具库
│   ├── api.ts           # API 客户端封装
│   ├── types.ts         # TypeScript 类型定义
│   └── utils.ts         # shadcn 工具函数
│
├── .env.local           # 环境变量（不提交）
├── next.config.ts       # Next.js 配置
├── tailwind.config.ts   # Tailwind 配置
├── components.json      # shadcn/ui 配置
└── package.json         # 依赖管理
```

## 核心功能

### 1. 任务看板 (/)

**文件**: `app/page.tsx`

**功能**:
- 5 列布局显示不同状态的任务
- 每 3 秒自动刷新
- 空状态提示
- 快速跳转到新建任务

**状态列**:
- TODO: 待执行
- RUNNING: 执行中
- DONE: 成功完成
- FAILED: 失败
- CANCELLED: 已取消

**数据流**:
```typescript
useSWR('/tasks', taskAPI.list, { refreshInterval: 3000 })
  → 按 status 分组
  → TaskBoard 组件
  → TaskCard 组件（点击跳转详情）
```

### 2. 新建任务 (/tasks/new)

**文件**: `app/tasks/new/page.tsx`, `components/TaskForm.tsx`

**表单字段**:
- Title（必填，最大 500 字符）
- Prompt（必填，多行文本）
- Workspace（下拉选择）
- Backend（单选：Claude Code / Codex CLI）

**验证逻辑**:
- 客户端验证：空值检查、长度限制
- 服务端验证：API 返回错误提示

**提交流程**:
```typescript
taskAPI.create(formData)
  → 成功 → router.push('/')
  → 失败 → 显示错误消息
```

### 3. 任务详情 (/tasks/[id])

**文件**: `app/tasks/[id]/page.tsx`, `components/LogStream.tsx`

**功能**:
- 显示任务完整信息
- 实时日志流（SSE）
- 状态徽章（带颜色）
- 操作按钮：
  - Cancel（RUNNING 状态）
  - Retry（FAILED 状态）

**SSE 日志流**:
```typescript
EventSource(logAPI.streamURL(runId))
  → 监听 'log' 事件 → 追加日志行
  → 监听 'complete' 事件 → 显示退出码
  → onerror → 5 秒后重连
```

**自动滚动**:
```typescript
useEffect(() => {
  logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
}, [logs]);
```

### 4. Runner 管理 (/runners)

**文件**: `app/runners/page.tsx`, `components/RunnerCard.tsx`

**功能**:
- 网格布局显示所有 Runner
- 状态指示器（绿色 ONLINE / 红色 OFFLINE）
- 显示能力列表
- 上次心跳时间

**刷新策略**:
- 每 10 秒自动刷新（比任务看板慢，因为变化较少）

## API 客户端

**文件**: `lib/api.ts`

### 配置

```typescript
const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000/api',
  headers: { 'Content-Type': 'application/json' },
});
```

### API 方法

**任务 API**:
- `taskAPI.list(status?)`: 获取任务列表
- `taskAPI.get(id)`: 获取单个任务
- `taskAPI.create(data)`: 创建任务
- `taskAPI.cancel(id)`: 取消任务
- `taskAPI.retry(id)`: 重试任务

**工作区 API**:
- `workspaceAPI.list()`: 获取工作区列表
- `workspaceAPI.create(data)`: 创建工作区

**Runner API**:
- `runnerAPI.list()`: 获取 Runner 列表

**日志 API**:
- `logAPI.get(runId)`: 获取历史日志
- `logAPI.streamURL(runId)`: 获取 SSE 流 URL

## TypeScript 类型

**文件**: `lib/types.ts`

### 主要类型

```typescript
// 任务状态枚举
enum TaskStatus {
  TODO = 'TODO',
  RUNNING = 'RUNNING',
  DONE = 'DONE',
  FAILED = 'FAILED',
  CANCELLED = 'CANCELLED',
}

// 后端类型枚举
enum BackendType {
  CLAUDE_CODE = 'claude_code',
  CODEX_CLI = 'codex_cli',
}

// 任务接口
interface Task {
  id: number;
  title: string;
  prompt: string;
  workspace_id: number;
  backend: BackendType;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  run_id?: number;
}

// 工作区接口
interface Workspace {
  workspace_id: number;
  path: string;
  display_name: string;
  runner_id: number;
  concurrency_limit: number;
}

// Runner 接口
interface Runner {
  runner_id: number;
  env: string;
  capabilities: string[];
  heartbeat_at: string;
  status: 'ONLINE' | 'OFFLINE';
  max_parallel: number;
}
```

## 样式规范

### Tailwind 类名约定

- 使用语义化类名
- 响应式设计：`md:`, `lg:` 前缀
- 深色模式：`dark:` 前缀（未启用）

### 组件样式模式

**卡片组件**:
```tsx
<Card className="hover:shadow-md transition-shadow">
  <CardHeader>...</CardHeader>
  <CardContent>...</CardContent>
</Card>
```

**状态徽章**:
```tsx
// 成功状态
<Badge className="bg-green-500">DONE</Badge>

// 失败状态
<Badge variant="destructive">FAILED</Badge>
```

## 开发指南

### 本地开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 启动生产服务器
npm start
```

### 环境变量

创建 `.env.local` 文件:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api
```

### 添加新组件

使用 shadcn/ui CLI:

```bash
npx shadcn@latest add [component-name]
```

### 代码规范

- 使用 TypeScript 严格模式
- 所有组件使用函数式组件
- 使用 'use client' 指令标记客户端组件
- 使用 ESLint 和 Prettier 格式化代码

## 性能优化

### SWR 缓存策略

- 自动去重请求
- 焦点重新验证
- 间隔轮询（任务列表 3s，Runner 10s）
- 乐观更新（取消/重试操作）

### Next.js 优化

- 自动代码分割
- 图像优化（Next.js Image）
- 静态生成（SSG）+ 客户端渲染（CSR）

### 未来优化方向

- 长日志虚拟滚动（react-window）
- React.memo 优化重渲染
- 实现深色模式
- 添加 Toast 通知
- 添加 Loading 骨架屏

## 部署

### 开发环境

```bash
npm run dev
```

### 生产环境

```bash
# 构建
npm run build

# 启动
npm start
```

### Docker 部署（计划中）

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

## 故障排查

### 常见问题

**1. API 请求失败 (CORS)**

检查后端 CORS 配置:
```python
# backend/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**2. SSE 日志流不工作**

- 确认 run_id 存在
- 检查浏览器控制台错误
- 验证后端日志端点返回正确的 SSE 格式

**3. 任务列表不刷新**

- 检查 SWR 配置的 refreshInterval
- 确认后端 API 正常响应
- 查看浏览器网络面板

**4. 构建失败 (Google Fonts)**

如果 Google Fonts 加载失败，使用系统字体:
```tsx
// app/layout.tsx
<body className="antialiased">
  {children}
</body>
```

## 未来改进 (M2+)

- [ ] 任务依赖可视化
- [ ] 批量操作（批量取消、删除）
- [ ] 任务搜索和过滤
- [ ] 额度监控仪表板
- [ ] 用户认证和权限
- [ ] WebSocket 替代 SSE（双向通信）
- [ ] 任务模板
- [ ] 导出日志
- [ ] 移动端适配
