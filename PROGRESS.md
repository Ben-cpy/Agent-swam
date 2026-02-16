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
