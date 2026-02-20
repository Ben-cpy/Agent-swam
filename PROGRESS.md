* **Copilot 任务卡队列修复（396fadd，2026-02-20）**：
  - 问题：copilot_cli 任务持续停留在 TODO/Queue，scheduler 周期性告警 “Runner does not support backend copilot_cli”。
  - 解决：LocalRunnerAgent 的 runner capabilities 改为从 BackendType 枚举动态生成，确保包含 copilot_cli；同时给 scheduler 增加“不支持 backend”告警去重，避免每轮刷屏。
  - 避免复发：新增 backend 时统一从单一枚举源派生能力列表，禁止在 runner 注册里写死字符串常量。
* **task-14 合并入主分支（447b446，2026-02-20）**：  
  - 问题：`task-14` 与 `main` 已分叉，需把“一键合并”功能安全并入主线。  
  - 解决：在 `main` worktree 执行 `git merge --no-ff task-14`，完成后端 merge API 与前端按钮改动合入，生成 merge commit `447b446`。  
  - 避免复发：后续同类任务统一先检查 `git worktree list` 和分叉计数，再在目标分支所在 worktree 完成合并。  
* **Task 内一键 Merge（b144ffa，2026-02-20）**：  
  - 问题：每次任务完成后都要手动重复输入“把当前 worktree 合并回主分支”的提示词，流程冗余且易漏。  
  - 解决：新增后端 POST /api/tasks/{id}/merge（固定 merge prompt + 复用 continue 重入机制，保持原 worktree），并在任务详情页新增 Merge to Base 按钮一键触发。  
  - 避免复发：把“高频固定动作”沉淀为显式 API + UI 按钮，不再依赖人工重复输入 prompt。  
* **2026-02-16 Code Review（0ceb2e8）**：指出 M1 高风险缺陷（后台任务复用请求级 DB session、取消状态竞态、错误枚举不匹配），给出具体整改点与测试建议，未改代码。
* **M1 问题修复（09319ff）**：一次性修复 6 个阻塞项：后台独立 DB session + 取消保护、修正退出码映射、强化 SQLite FK 与 API 校验、去硬编码日志 URL、修前端类型/调用与 lint 问题；新增 `tests/verify_m1_fixes.py` 并要求进 CI。
* **启动与工作区清理（e7a22bf）**：重写 README 为最小启动手册；`setup_env.sh` 去硬编码、支持非交互与 ensurepip 修复；新增一键清理脚本；测试脚本兼容 Windows 文件锁重试。
* **工作区管理（82c4448）**：新增 UI/后端支持工作区增删查，扩展类型为 `local/ssh/ssh_container`，完善校验与路径规范化；修复枚举存储不一致导致的 500（改为 value 持久化并兼容旧值）；补 SQLite 迁移。
* **Windows Codex 与任务删除（269a09e）**：解决 WinError2（不再依赖 PowerShell alias，改为解析真实可执行文件路径如 `.cmd`）；补齐任务删除 API 与前端按钮。
* **M3 配额监控（2026-02-17，pending）**：实现配额/用量采集与“配额耗尽即停止”：新增 QuotaState、`FAILED_QUOTA`、`usage_json`；两适配器解析流事件获取用量并识别 quota/rate-limit；调度前检查配额；提供 `/api/quota` 与前端告警/管理/重试。
* **Velvet 简化与 Worktree 隔离（8831cad）**：认为状态/页面过复杂，**回退简化**：移除配额/runner/usage 页面与路由；任务状态统一为 `TODO/RUNNING/DONE/FAILED` 并迁移旧状态；引入每任务 `branch_name/worktree_path`，执行前自动建 git worktree 隔离；UI 回到 4 列看板并展示 worktree 信息。
* **verl 三特性并行开发（7a5a073，2026-02-18）**：用 3 个 git worktree 并行实现 3 个 Feature，全部指标验证通过后合并回 main：
  - `feature/model-selection`（3a0d149）：`/api/models` 端点+10分钟缓存；Task 新增 `model` 列；ClaudeCodeAdapter/CodexAdapter 透传 `--model` 参数；前端 TaskForm 动态 model 下拉框。
  - `feature/usage-aggregation`（bebd636）：`/api/usage` 端点聚合 Run.usage_json；同时支持 claude_code（cost_usd）和 codex_cli（total_tokens）；前端 UsageSummary 卡片置于 Dashboard 顶部，SWR 30s 刷新。
  - `feature/tmux-terminal`（3be1bec）：Run 新增 `tmux_session` 列；SSH workspace 任务包裹 tmux 执行；`/api/tasks/{id}/terminal` WebSocket 端点（asyncssh）实现 PTY 双向中继；前端 `/tasks/[id]/terminal` xterm.js 终端页；任务详情页新增"Open Terminal"按钮（仅 SSH workspace 可见）。
* **Review 状态 + 直接合并 + 全局并发设置（11be924，2026-02-20）**：
  - 问题：任务完成即 DONE，缺少人工 Review 阶段；Merge 依赖 AI 二次执行；调度仍按串行导致 worktree 并行能力未利用。
  - 解决：新增 TO_BE_REVIEW 状态流（RUNNING 成功后进入 Review）；POST /api/tasks/{id}/merge 改为后端直接 git merge + 清理 worktree；新增 /api/settings 与前端 /settings 管理全局 workspace_max_parallel（默认 3），并立即覆盖 runner/workspace 并发；scheduler 按 workspace/runner 限额并行派发。
  - 避免复发：涉及状态机与调度策略升级时，必须同步检查后端枚举、接口约束、前端状态映射和可见性条件，避免只改单点导致流程断裂。
* **长 Prompt 任务失败修复（31d33e7，2026-02-20）**：
  - 问题：Windows 下将超长 prompt 作为命令行参数传给 claude/codex 时，任务会快速失败（命令行长度上限风险）。
  - 解决：后端适配器改为通过 stdin 传入 prompt（codex exec - + claude --input-format text），并在前后端统一 prompt_max_chars=65536 校验与计数提示。
  - 避免复发：后续对大文本输入统一采用 stdin/文件通道，不再依赖命令行参数承载长内容；长度阈值统一由配置常量管理。
* **Execution Logs 自动滚动打断操作修复（729ac03，2026-02-20）**：
  - 问题：任务详情页日志持续更新时，组件每次通过 `scrollIntoView` 触发整页滚动，导致页面焦点频繁被拖回日志区，影响用户在主界面操作。
  - 解决：`LogStream` 改为监听日志容器滚动位置，仅在“用户当前接近底部”时自动跟随，且只滚动日志容器自身（`scrollTop`），不再驱动页面滚动。
  - 避免复发：流式日志/聊天窗口类组件统一采用“sticky-to-bottom”策略，不直接在更新时调用可能影响整页滚动的 `scrollIntoView`。

* **Windows CLI shell 优先级回退（5777682，2026-02-20）**：
  - 问题：在 Windows 环境下，CLI 执行链路缺少显式 shell 优先级策略，用户希望固定优先使用 Git Bash，并在不可用时自动回退。
  - 解决：在 `backend/core/adapters/cli_resolver.py` 新增 shell 探测与命令变体构建（git-bash > cmd > powershell），并在 `BackendAdapter.run_subprocess` 中按优先级尝试执行；命令不可用时自动回退，最终保留 direct exec 兜底；`claude/codex/copilot` 适配器均接入 `cli_name`。
  - 避免复发：Windows 端新增 CLI 或调整执行器时，统一走同一套 shell-priority 解析逻辑，禁止在各适配器内各自实现 shell 选择。
  - Commit: `5777682`
