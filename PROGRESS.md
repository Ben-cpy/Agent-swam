## 2026-02-16 - Code Review Findings (Commit: 0ceb2e8)
- Problem: M1 execution path has high-risk defects (background task reuses request-scoped DB session, cancel can be overwritten by late runner completion, and adapter returns CANCELLED which is not in ErrorClass).
- Fix: Performed code review and identified exact file/line locations with actionable remediations; no code change applied in this step.
- Prevention: Add integration tests for async execution lifecycle, cancellation race, and exit-code/error-class mapping; enforce DB FK checks and endpoint-level FK validation.
- Git Commit ID: 0ceb2e8

## 2026-02-16 - M1 Issues 1-6 Fixed (Commit: 09319ff)
- Problem: Six blocking issues were present: background task used request-scoped DB session, cancellation state could be overwritten, exit-code mapping returned invalid enum key, FK integrity was weak at API/db level, log streaming URL was hardcoded, and frontend lint/type checks failed.
- Fix: Refactored executor lifecycle to use independent background sessions plus cancellation guard, enabled SQLite FK pragma and API FK validations, normalized frontend API typing/URL handling, removed React anti-patterns causing lint errors, and added `tests/verify_m1_fixes.py` to validate critical behavior.
- Prevention: Keep `tests/verify_m1_fixes.py` in CI, require `npm run lint && npm run build` on frontend and backend startup/verify scripts before merge, and avoid introducing untracked source by keeping `.gitignore` path rules scoped.
- Git Commit ID: 09319ff

## 2026-02-16 - Startup Simplification & Workspace Cleanup (Commit: e7a22bf)
- Problem: Startup docs were overloaded and partially garbled, setup script depended on hardcoded Python path and interactive prompts, and local runtime artifacts/logs made the workspace noisy.
- Fix: Rewrote `README.md` to a minimal startup runbook, made `scripts/setup_env.sh` robust (auto Python discovery + non-interactive + ensurepip recovery), added `scripts/clean_workspace.sh` for one-command cleanup, and hardened `tests/verify_m1_fixes.py` DB reset retry for Windows file-lock timing.
- Prevention: Keep startup docs focused on a single happy path, avoid hardcoded user paths, and prefer scripted cleanup over manual deletion.
- Git Commit ID: e7a22bf

## 2026-02-16 - Workspace Management (Local/SSH/Container) (Commit: 82c4448)
- Problem: Users could not self-manage workspaces in UI, and backend only validated local paths, so SSH/container workspace registration was impossible.
- Fix: Added `/workspaces` management page (create + list), introduced workspace types (`local`, `ssh`, `ssh_container`) with conditional fields, extended backend schemas/models/API validation and canonical path generation, and added SQLite-compatible schema migration for new columns.
- Additional Fix: Resolved `/api/workspaces` 500 caused by enum storage mismatch by switching SQLAlchemy enum mapping to value-based persistence and normalizing legacy enum literals.
- Prevention: Keep enum persistence strategy explicit (`values_callable`), and include startup migration checks when adding nullable columns in SQLite-backed environments.
- Git Commit ID: 82c4448

## 2026-02-16 - Codex WinError2 + Task Delete Flow (Commit: 269a09e)
- Problem: Local tasks using Codex failed with `Internal error: [WinError 2]` on Windows because subprocess execution could not resolve PowerShell command aliases (`codex`/`claude`) reliably; task deletion was also missing.
- Fix: Added explicit cross-platform CLI resolver and switched adapters to execute real binaries (`codex.cmd` / `claude.cmd` on Windows), added clearer CLI-not-found handling, and implemented task delete API + frontend delete button in task detail page.
- Prevention: Never rely on shell aliases for subprocess execution in Python on Windows; always resolve concrete executable path first.
- Git Commit ID: 269a09e

## 2026-02-17 - M3 Quota Monitoring & Stop-on-Exhaustion (Commit: pending)
- Problem: No usage tracking or quota monitoring; tasks ran without cost awareness, and quota exhaustion was not detected or handled.
- Fix: Implemented full M3 milestone:
  - Added `QuotaState` model, `FAILED_QUOTA` task status, `QUOTA` error class, `usage_json` on runs
  - Claude adapter parses stream-json `result` events for cost/usage, detects `rate_limit_error` from `error` events
  - Codex adapter parses `turn.completed` events for token usage, detects quota errors from `error` events
  - Both adapters fall back to plain-text keyword scanning for quota signals
  - Executor persists `usage_json`, marks tasks `FAILED_QUOTA` on quota errors, updates `quota_states` table
  - Scheduler checks `quota_states` before dispatching—skips tasks whose provider is `QUOTA_EXHAUSTED`
  - New `/api/quota` endpoints (list + reset) for manual quota recovery
  - Frontend: global red alert bar, 6-column kanban with `FAILED_QUOTA`, quota management page with reset buttons, retry support for quota-failed tasks
- Prevention: Use adapter instance attributes (not yield interface changes) for side-channel data; always use `values_callable` for new enum columns; seed default rows at startup to avoid null queries.
- Git Commit ID: pending
