# UI Enhancement Plan

## Tasks Overview

1. Agent icons in task cards
2. Task elapsed-time timer (running tasks)
3. Remove "Base Branch" from New Task form
4. New tasks for a busy workspace go to TODO (queued, no timer)
5. Delete workspace button in Workspace Management

---

## 1. Agent Icons in Task Cards

**Files**: `frontend/components/TaskCard.tsx`, `frontend/public/` (copy icons here)

**Steps**:
- Copy `img/Claude_AI_symbol.svg` and `img/ChatGPT_logo.svg` into `frontend/public/` so Next.js can serve them as static assets.
- In `TaskCard.tsx`, replace the text badge (`CC` / `CX`) with `<img>` tags:
  ```tsx
  const getBackendIcon = (backend: BackendType) => {
    switch (backend) {
      case BackendType.CLAUDE_CODE:
        return <img src="/Claude_AI_symbol.svg" alt="Claude" className="w-5 h-5" />;
      case BackendType.CODEX_CLI:
        return <img src="/ChatGPT_logo.svg" alt="Codex" className="w-5 h-5" />;
      default:
        return <span className="text-xs font-semibold">AI</span>;
    }
  };
  ```
- Keep the surrounding `<span>` container but remove the border/text styling when showing an image.

---

## 2. Task Elapsed-Time Timer

**Files**: `frontend/components/TaskCard.tsx`

**Steps**:
- Add a `useEffect` + `useState` hook in `TaskCard` that ticks every second when `task.status === TaskStatus.RUNNING`.
- Derive start time from the run's `started_at` field. The task API response includes `run_id`; fetch or expose `started_at` from the task response, or use `task.updated_at` as a proxy when status changed to RUNNING.
  - Preferred: extend `TaskResponse` type to include `started_at` from the latest run (backend already returns it via the `/api/runs` or logs endpoint).
  - If backend plumbing is needed: modify `TaskResponse` schema in `backend/api/tasks.py` to include `run_started_at` from the joined Run row.
- Display elapsed time in `mm:ss` (or `hh:mm:ss` for long tasks) only when status is `RUNNING`.
- Stop and freeze the display when task transitions to `DONE` or `FAILED`.

**Backend change** (if needed): Add `run_started_at: Optional[datetime]` to `TaskResponse` pydantic model and populate via a join on the `runs` table.

---

## 3. Remove "Base Branch" from New Task Form

**File**: `frontend/components/TaskForm.tsx`

**Steps**:
- Delete the entire `<div>` block for the `branch_name` field (currently lines ~274–287).
- Remove `branch_name` from `formData` state initialization and from the submit payload (or keep it in the submit payload as `undefined`/omitted — the backend already treats it as optional and auto-detects).
- No backend changes needed.

---

## 4. New Tasks Queue Behind Running Task per Workspace

**Context**: Each workspace has `concurrency_limit = 1`. A new task submitted while a workspace is busy gets status `TODO` and the executor picks it up when the running task finishes. This is already the backend behavior. The UI change is to make this visible.

**Files**: `frontend/components/TaskBoard.tsx`, `frontend/components/TaskCard.tsx`

**Steps**:
- In the "To Do" column of `TaskBoard`, for tasks whose workspace already has a `RUNNING` task, show a small "queued" badge or label (e.g., grey `Queued` chip).
- Timer should NOT start for TODO tasks — only for RUNNING tasks (already handled by step 2).
- Optional: sort TODO tasks by `created_at` so users can see queue order per workspace.

---

## 5. Delete Workspace Button

**Files**: `frontend/components/WorkspaceManager.tsx`, `backend/api/workspaces.py`

### Backend
- Add `DELETE /api/workspaces/{workspace_id}` endpoint in `backend/api/workspaces.py`:
  - Guard: reject if workspace has any `RUNNING` tasks.
  - Delete the workspace row (cascade or manual cleanup of related tasks as appropriate).
  - Return `204 No Content` on success.

### Frontend
- In `WorkspaceManager.tsx`, inside the workspace card header flex row (after the type `Badge`), add a delete `<Button>` with a trash icon:
  ```tsx
  import { Trash2 } from 'lucide-react';
  // ...
  <Button
    variant="ghost"
    size="icon"
    className="text-destructive hover:text-destructive"
    onClick={() => handleDeleteWorkspace(ws.workspace_id)}
  >
    <Trash2 className="w-4 h-4" />
  </Button>
  ```
- Add `handleDeleteWorkspace` function: calls `DELETE /api/workspaces/{id}`, then calls `mutate()` to refresh the list.
- Add a confirmation dialog (use `window.confirm` or a shadcn `AlertDialog`) before deleting.

---

## Verification

1. **Agent icons**: Open Task Board — Claude tasks show the Claude SVG, Codex tasks show the ChatGPT SVG.
2. **Timer**: Start a task. The card shows a live `mm:ss` counter. When it finishes the counter freezes.
3. **No base branch**: Open New Task dialog — no "Base Branch" field visible. Task still creates with auto-detected branch.
4. **Queued tasks**: Submit two tasks to the same workspace back-to-back. First goes RUNNING, second stays TODO with "Queued" indicator and no timer.
5. **Delete workspace**: Go to `/workspaces`. Click trash icon on a workspace. Confirm dialog appears. After confirmation the workspace disappears from the list.
