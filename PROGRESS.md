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
