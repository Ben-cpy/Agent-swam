# CI/CD Setup (GitHub)

## Goal
- Run backend and frontend checks on every push/PR to prevent regressions.
- Produce a delivery artifact automatically only after successful pushes to `main`.

## Workflow File
- `.github/workflows/ci-cd.yml`

## CI
Triggers:
- `push` to any branch
- `pull_request` targeting `main`
- `workflow_dispatch`

What runs:
- Backend (`ubuntu-latest` + `windows-latest`, Python 3.9)
  - Install `backend/requirements.txt`
  - `python -m pip check`
  - `python -m compileall backend tests`
  - `python tests/test_retry_inplace.py`
  - `python tests/test_startup.py`
- Frontend (`ubuntu-latest`, Node 20)
  - `npm ci`
  - `npm run lint`
  - `npm run build`

Concurrency:
- New commits on the same ref cancel older in-progress runs.

## CD
Trigger:
- Only on `push` to `main`, after all CI jobs pass.

What runs:
- Build frontend production output (`next build`)
- Assemble and upload an artifact (14-day retention) with:
  - `backend/`
  - `scripts/`
  - `frontend/.next`
  - `frontend/package.json`
  - `frontend/package-lock.json`
  - `frontend/next.config.ts`
  - `dist/delivery-manifest.txt` (commit + build time)

## Recommended Branch Protection
Configure `main` branch protection in GitHub and require these checks:
- `Backend CI (py3.9 / ubuntu-latest)`
- `Backend CI (py3.9 / windows-latest)`
- `Frontend CI (Node 20)`

Recommended toggles:
- Require pull request before merging
- Require branches to be up to date before merging

## Troubleshooting
- Backend failure: inspect `Install backend dependencies` and both `tests/*.py` steps.
- Frontend failure: inspect `lint` and `build` logs.
- CD failure: inspect `Assemble delivery bundle` and `next build` logs.
