* **异步 SQLAlchemy 数据库稳定性修复（65c5e4a，2026-02-23）**：
  - 问题：高并发场景下频繁出现 "Database is locked" 错误与 "detached instance ... is not bound to any database session" 异常，数据库操作不稳定。
  - 根本原因：①Task.run relationship 的 `post_update=True` 在异步环境中导致额外 UPDATE 和竞态条件；②`expire_on_commit=False` 与 `post_update=True` 组合引发对象分离问题；③三个关键函数（continue_task/merge_task/delete_task）在 commit 后使用可能分离的对象。
  - 解决：①移除 `post_update=True` 从 models.py 的 Task.run relationship；②改为 `expire_on_commit=True` 以强制正确的对象生命周期管理；③统一 session 使用模式：commit 前保存所有需要的属性值，commit 后仅使用保存的值；④移除所有不必要的 `db.refresh()` 调用（create_task/retry_task/_update_task/continue_task/mark_task_done 共 5 处）；⑤merge_task/delete_task 在 commit 前保存 worktree_path/workspace，commit 后调用 _remove_worktree 时仅使用保存值。
  - 避免复发：异步 ORM 操作必须遵循"获取所需值→commit→使用保存值"的严格顺序，禁止 commit 后访问任何 ORM 对象属性；新增 session 管理改动时强制 review session 生命周期。
  - Commit: `65c5e4a`

* **Merge 流程健壮性补强（11199d3，2026-02-21）**：
  - 问题：用户在点击任务 Merge 时仍会遇到高频失败，包括基线 workspace/任务 worktree 存在未提交改动、历史 merge 残留状态阻塞、worktree 路径失效后无法按分支继续合并，以及 AI 冲突兜底仅按退出码判定导致误报失败。
  - 解决：重构 backend/api/tasks.py 合并链路，新增“合并前自动恢复”与“可选 worktree”机制：先自动 merge --abort 清理遗留状态；对 task/workspace 两侧未提交改动自动提交后再 merge；worktree 缺失时允许直接按 task 分支合并；冲突时仅触发一次 AI fallback，并在 AI 后按 Git 实际状态（unmerged files 与 MERGE_HEAD）做最终判定。同步在 backend/core/adapters/codex.py 为非交互执行增加 --ask-for-approval never，避免自动兜底卡在审批提示。新增 tests/test_merge_robust.py 回归场景覆盖基线脏工作区自动提交与无 worktree 路径分支合并。
  - 避免复发：Merge 入口必须遵循“规则优先、AI兜底、状态可恢复”的统一流程，且每次改动都要覆盖真实失败边界（base dirty/worktree missing/stale MERGE_HEAD）并回归验证。
  - Commit: `11199d3`

* **任务标题修改 405 修复（66310ee，2026-02-21）**：
  - 问题：任务详情页保存标题时报错 `Failed to update title: Method Not Allowed`，`PATCH /api/tasks/{id}` 在部分环境存在方法受限导致失败。
  - 解决：后端新增 `POST /api/tasks/{id}/rename` 复用同一更新逻辑；前端 `taskAPI.updateTitle` 改为优先调用 POST，并在后端尚未升级时对 404 回退到原 PATCH。
  - 避免复发：对关键写操作提供“兼容方法通道”（如 POST action endpoint）与客户端回退策略，避免被网关/代理的 HTTP 方法限制卡死核心功能。
  - Commit: `66310ee`
* **task-1 合并入主分支（7848387，2026-02-21）**：
  - 问题：在 `main` 合并 `task-1` 时，`PROGRESS.md` 出现并行更新冲突，阻塞自动合并。
  - 解决：手动解决 `PROGRESS.md` 冲突，保留 `main` 的 CI/CD 记录与 `task-1` 的通知开关记录后完成 merge commit `7848387`。
  - 避免复发：并行分支持续写同一沉淀文档时，合并前优先做一次 `rebase main` 或先拆分独立条目，降低文本冲突概率。
  - Commit: `7848387`

* **Settings 通知开关（9411478，2026-02-21）**：
  - 问题：`TO_BE_REVIEW` 全局弹窗默认始终开启，缺少用户侧开关，无法按偏好关闭通知。
  - 解决：新增 `frontend/lib/reviewNotificationSettings.ts` 管理本地持久化开关；`frontend/app/settings/page.tsx` 增加通知开关；`frontend/components/ToBeReviewNotifier.tsx` 接入开关监听，关闭时停止轮询与弹窗，开启后即时生效。
  - 避免复发：对全局提醒类能力默认提供显式开关，并让通知触发组件直接订阅该配置，避免“设置页改了但运行态不生效”。
  - Commit: `9411478`
* **Review 通知漏报边界修复（1cea57b，2026-02-21）**：
  - 问题：如果任务在两次轮询之间快速完成，下一次拉取时可能“首次出现即 TO_BE_REVIEW”，原逻辑会因为缺少上一状态而不弹窗。
  - 解决：在 `frontend/components/ToBeReviewNotifier.tsx` 调整跃迁判断：首次观察到任务且当前为 `TO_BE_REVIEW` 也触发通知。
  - 避免复发：状态变化提醒逻辑需覆盖“首次观测态”场景，避免仅依赖严格的前后态对比。
  - Commit: `1cea57b`
* **TO_BE_REVIEW 全局弹窗通知（56a0913，2026-02-21）**：
  - 问题：任务进入 `TO_BE_REVIEW` 后，只有在看板/详情页内才能看到状态变化，切到其他站内页面时容易错过待审核任务。
  - 解决：新增 `frontend/components/ToBeReviewNotifier.tsx` 全局客户端通知器并挂载到 `frontend/app/layout.tsx`；通过 SWR 轮询任务列表，检测任务状态由非 `TO_BE_REVIEW` 跃迁到 `TO_BE_REVIEW` 时触发浏览器 Notification 弹窗（`silent: true`，点击跳转任务详情）。
  - 避免复发：对关键状态流转（如待审核、失败、人工介入）统一提供跨页面可见提醒，避免仅依赖当前页面局部 UI 提示。
  - Commit: `56a0913`
* **失败任务重试反馈与按钮样式优化（7059f9a，2026-02-21）**：
  - 问题：任务详情页中 FAILED 任务点击 `Retry Task` 后会触发重试，但界面没有成功反馈，且按钮默认黑色视觉不匹配当前页面风格。
  - 解决：在 `frontend/app/tasks/[id]/page.tsx` 新增 3 秒自动消失的重试成功提示条（`Task re-queued. Execution will start shortly.`），并将 `Retry Task` 按钮改为 GitHub 风格蓝色（`#0969da`，hover `#0860ca`），同时补充 `Retrying...` 加载文案。
  - 避免复发：对"状态变更触发后台动作"的按钮统一增加即时 UI 反馈（toast/提示条/状态文案），避免用户误判点击无效。
  - Commit: `7059f9a`
* **Retry 语义加固与回归脚本（2b7cd28，2026-02-21）**：
  - 问题：用户反馈 FAILED 任务点击 Retry 后仍可能出现"新任务/新 worktree"心智负担，需要进一步加固"原任务原地重试"语义并增加可回归验证。
  - 解决：后端在 `retry/continue` 两个入口统一清理 `run_id` 并写入 in-place 重排队日志；新增 `tests/test_retry_inplace.py`，验证 retry 后任务数量不增加、`id/title/worktree_path` 不变、状态 `FAILED -> TODO`。
  - 避免复发：涉及状态机行为（重试/继续）必须配套最小回归脚本，至少覆盖"实体不复制、上下文不丢失、状态可观测"三项断言。
  - Commit: `2b7cd28`
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
* **FAILED 任务重试复用同一 Task/Worktree（62bcfdd，2026-02-20）**：
  - 问题：任务详情页点击 Retry 会创建新任务（标题追加 Retry）并新建 worktree，导致同一失败任务上下文被拆分。
  - 解决：将 `POST /api/tasks/{id}/retry` 改为原任务原地重排队（`FAILED -> TODO`），复用既有 `worktree_path`，且不再创建新 Task；前端 Retry 改为留在当前任务页并 `mutate()` 刷新状态。
  - 避免复发：涉及“重试”语义时优先定义为状态机流转而非复制实体；仅在明确需要历史分叉时才创建新任务。
* **task-8 合并入主分支（0747361，2026-02-20）**：
  - 问题：`task-8` 合并到 `main` 时在 `PROGRESS.md` 出现内容冲突。
  - 解决：手动合并冲突块，保留双方有效记录后完成 merge commit。
  - 避免复发：并行分支都维护同一沉淀文档时，合并前先 rebase 或提前拆分独立条目，降低冲突概率。
  - Commit: `0747361`

* **Windows 终端优先级鲁棒性增强（46b4fa0，2026-02-21）**：
  - 问题：用户反馈在 Windows 下 `codex`、`copilot` 运行时偏向 PowerShell，希望默认优先 `git bash > cmd > powershell`，并在不同安装路径下保持稳定回退。
  - 解决：增强 `backend/core/adapters/cli_resolver.py`：扩展 Git Bash 探测路径（Program Files/LocalAppData/PATH/环境变量）、去重校验并统一优先级；`claude/codex/copilot` 适配器统一注入 `COMSPEC/SHELL` 覆盖，`Claude` 额外注入 `CLAUDE_CODE_SHELL`；`Codex` 额外传入 `shell_environment_policy.set.*` 作为 shell tool 环境提示。
  - 避免复发：Windows shell 选择统一走 `cli_resolver` 单一入口，新增 CLI/适配器时禁止各自硬编码 shell 逻辑；任何变更都先验证当前机型解析顺序输出。
  - Commit: `46b4fa0`

* **CI/CD 基线与交付产物流水线（cb78637，2026-02-21）**：
  - 问题：仓库缺少 GitHub 端自动质量闸门，新改动可能在合并后才暴露后端回归或前端构建问题；同时无主分支自动交付产物。
  - 解决：新增 `.github/workflows/ci-cd.yml`，CI 覆盖后端（ubuntu/windows + Python 3.9、依赖检查、编译、回归脚本）和前端（Node 20、lint、build）；CD 在 `main` push 且 CI 通过后自动打包并上传 delivery artifact。补充 `CI_CD.md` 说明触发条件、检查项和分支保护建议。
  - 避免复发：后续新增功能必须先补对应测试/构建命令并纳入 workflow；合并策略统一依赖必过检查，禁止绕过 CI 直接入主分支。
  - Commit: `cb78637`

* **空悬 Task 自动修复与 Worktree 健壮性增强（05420fd，2026-02-21）**：
  - 问题：用户在文件管理器/CMD 手工删除 worktree 或外部完成分支合并后，DB 仍保留旧 `worktree_path` 与 `TO_BE_REVIEW` 任务，前端会出现空悬 task；同时执行器会把存在但非 git worktree 的目录误判为可复用。
  - 解决：新增 `backend/core/task_reconciler.py` 并接入 scheduler 每轮巡检，自动清理失效 worktree 引用、执行 `git worktree prune`、并将已外部合并/分支缺失的 `TO_BE_REVIEW` 任务自动闭环为 `DONE`；同时强化 `executor._create_worktree`，仅复用有效 git worktree，空目录自动清理，异常路径自动回退到恢复路径；`merge` 接口改为在 worktree 缺失时仍可按分支完成合并，并在清理阶段补 `worktree prune`。
  - 避免复发：所有路径存在即复用的逻辑必须先做 git worktree 有效性校验；状态机需定期与 Git 真实状态对账，避免仅依赖 DB 字段导致长期空悬。
  - Commit: `05420fd`

* **Claude/Codex 超长单行日志触发 LimitOverrunError 修复（76ef41c，2026-02-21）**：
  - 问题：`asyncio` 的 `StreamReader` 默认单行限制约 64KB，Claude Code stream-json 在大输出场景会产生超长单行，导致 `LimitOverrunError: Separator is found, but chunk is longer than limit`，任务中断。
  - 解决：在 `backend/core/adapters/base.py` 的 `asyncio.create_subprocess_exec` 增加 `limit=10 * 1024 * 1024`，将 subprocess stdout 的 `StreamReader` 上限提升到 10MB。
  - 避免复发：所有基于 `readline()` 的流式子进程读取必须显式设置合理 `limit`，并在接入新 CLI/新输出协议时评估单行峰值大小后统一参数。
  - Commit: `76ef41c`

* **任务审批状态回归修复（22438ec，2026-02-21）**：
  - 问题：为修复空悬 task 引入的 reconciler 自动闭环逻辑，导致新任务在未审批场景可能被自动从 `TO_BE_REVIEW` 置为 `DONE`，并触发 worktree/分支清理，出现”未合并主干却被关单”的高风险行为。
  - 解决：移除 `backend/core/task_reconciler.py` 中 `TO_BE_REVIEW -> DONE` 自动状态推进与自动删分支逻辑，只保留失效 worktree 引用清理；新增 `POST /api/tasks/{id}/mark-done` 手动完结接口；前端任务详情页新增 `Mark as Done` 按钮；回归脚本更新为”reconciler 不自动关单”，并新增 `tests/test_mark_done.py`。
  - 避免复发：reconciler 只能做”引用修复/一致性修复”，不得做审批语义状态推进；任何会把任务置为 `DONE` 的路径必须是显式用户动作（merge 或 mark done），并配套回归测试覆盖。
  - Commit: `22438ec`

* **task-7 数据库稳定性修复合并入主分支（4971f1c，2026-02-23）**：
  - 问题：task-7 worktree 包含 3 个关键数据库稳定性修复提交，需要合并入主分支。
  - 解决：在主分支执行 `git merge worktree-task-7-db-fixes --no-ff`，包含：异步 SQLAlchemy 稳定性修复、`post_update=True` 移除、session 生命周期正确化、数据库锁定竞态条件修复；同时引入 `DATABASE_FIX_SUMMARY.md` 文档；合并无冲突，生成 merge commit 后清理 worktree。
  - 避免复发：task worktree 合并前必须验证 `git worktree list`，确认分支名称后执行合并并清理资源。
  - Commit: `4971f1c`

* **2026-02-23 回归排查（范围：`ede69ae..88983c3`）**：
  - 问题：自 `65c5e4a` 引入 `expire_on_commit=True` 后，多个接口与调度路径在 commit 后继续访问 ORM 对象，触发 `MissingGreenlet`；`retry/merge/mark-done/delete` 出现“HTTP 500 但数据库状态已变更”。
  - 解决：完成端到端复现（API + scheduler + 三后端 CLI 实测），确认根因集中在 post-commit 访问过期实例与清理阶段使用过期 `workspace`；并确认 `api/models` 中 codex 默认模型（`o4-mini`）在当前 ChatGPT 账号不可用会直接失败。
  - 避免复发：若坚持 `expire_on_commit=True`，所有 commit 后返回值与清理逻辑必须改为“重新查询/冻结原始标量快照”；关键接口必须新增“返回码与最终状态一致性”回归测试；模型列表需从 CLI/账号能力动态探测，不得硬编码默认可用模型。
  - Related Commit IDs: `65c5e4a`, `88983c3`

* **任务生命周期 MissingGreenlet 回归修复（7247290，2026-02-24）**：
  - 问题：任务调度与多个状态接口在 commit 后访问 ORM 对象，触发 `MissingGreenlet`，表现为任务卡 `RUNNING`、`retry/patch/mark-done/delete` 返回 500 但状态已落库。
  - 解决：`sessionmaker` 回退为 `expire_on_commit=False`；`tasks` 接口在 commit 后统一通过 `_load_task_with_run` 重新查询返回；merge/mark-done/delete 的 worktree 清理改为使用 `WorkspaceCleanupRef` 快照，避免 post-commit 访问过期 workspace；`executor` 在 commit 前缓存运行参数，避免后续读取潜在过期字段；`/api/models` 的 codex 默认模型调整为 `gpt-5.1-codex` 并修复 claude CLI 探测路径解析。
  - 避免复发：异步 SQLAlchemy 场景下，任何 commit 后逻辑都禁止直接依赖 ORM 实例状态；关键路径必须覆盖“HTTP 返回码与最终状态一致性”回归用例。
  - Commit: `7247290`

* **SQLite 锁冲突与连接取消异常修复（a1aa45f，2026-02-24）**：
  - 问题：高频 `GET /api/logs/{id}/stream` + 调度写入并发时出现 `(sqlite3.OperationalError) database is locked`，并伴随 `get_db` 结束阶段 `no active connection` / `CancelledError`。
  - 解决：`backend/database.py` 移除请求级自动 `commit`，改为显式提交策略并在清理阶段安全 rollback/close；为 SQLite 连接启用 `WAL`、`busy_timeout=30000`、`timeout=30`；`backend/api/logs.py` 的 SSE 轮询改为每轮短生命周期 session，避免长连接持有事务。
  - 避免复发：流式接口禁止复用长生命周期 DB session；SQLite 并发场景默认开启 WAL + busy_timeout；事务提交边界统一由写接口显式控制。
  - Commit: `a1aa45f`

* **任务完成全局通知扩展（dba1e2d，2026-02-24）**：
  - 问题：当前前端仅在任务进入 `TO_BE_REVIEW` 时弹窗，任务执行后若直接失败或已完成，用户切到其他浏览器标签页时容易错过状态变化。
  - 解决：扩展 `frontend/components/ToBeReviewNotifier.tsx` 为“任务完成通知器”，在任务从非终态进入 `TO_BE_REVIEW/DONE/FAILED` 时触发系统通知；同步更新 `settings` 文案为“Notify when task run completes”；通知配置工具改为 completion 语义并保留旧 key/事件导出兼容。
  - 避免复发：全局提醒逻辑应按“终态集合”建模，不应绑定单一状态；涉及配置项重命名时保留向后兼容导出，避免用户本地设置失效。
  - Commit: `dba1e2d`
