# Task Management System Refactoring Plan

## Overview
This plan implements five major changes to simplify the UI and add git worktree support for task isolation.

## Requirements Summary
1. Remove quota and runner features from UI and backend
2. Automatically create git worktrees for ALL tasks using auto-detected base branch
3. Simplify task statuses (merge FAILED_QUOTA and CANCELLED into FAILED)
4. Improve Task Board spacing (increase gaps between cards, reduce padding within cards)
5. Worktrees are kept after task completion for manual review/merge

---

## Phase 1: Remove Quota/Runner/Usage Features

### Frontend Deletions
**Files to delete completely:**
- `frontend/app/quota/page.tsx` - Quota management page
- `frontend/app/runners/page.tsx` - Runners status page
- `frontend/app/usage/page.tsx` - Usage statistics page
- `frontend/components/QuotaAlert.tsx` - Banner alert component

### Frontend Modifications

**File: `frontend/components/Navbar.tsx`**
- Remove navigation links for '/runners', '/quota', and '/usage' from navLinks array
- Keep only: Task Board, New Task, Workspaces

**File: `frontend/app/layout.tsx`**
- Remove `QuotaAlert` import
- Remove `<QuotaAlert />` from layout (should be around line 20)

**File: `frontend/lib/api.ts`**
- Remove `quotaAPI` object and its exported functions
- Remove `usageAPI` object and its exported functions
- Remove `runnerAPI` object and its exported functions
- Remove unused type imports: `QuotaState`, `Runner`, `UsageData`

### Backend Deletions
**Files to delete completely:**
- `backend/api/quota.py`
- `backend/api/usage.py`
- `backend/api/runners.py`

### Backend Modifications

**File: `backend/main.py`**
- Remove imports for quota, usage, runners routers
- Remove `app.include_router(quota.router)`
- Remove `app.include_router(usage.router)`
- Remove `app.include_router(runners.router)`
- Remove quota state seeding logic (lines 52-67 approximately)

---

## Phase 2: Simplify Task Statuses

### Backend Changes

**File: `backend/models.py`**
- Modify `TaskStatus` enum:
  - Remove `FAILED_QUOTA = "FAILED_QUOTA"`
  - Remove `CANCELLED = "CANCELLED"`
  - Keep only: `TODO`, `RUNNING`, `DONE`, `FAILED`

**File: `backend/core/executor.py`**

Modify `_persist_execution_result()` method:
- When task is cancelled: Set status to `FAILED` instead of `CANCELLED`
- When quota error occurs: Set status to `FAILED` instead of `FAILED_QUOTA`
- Keep the `error_class` field for detailed tracking (ErrorClass.QUOTA, ErrorClass.UNKNOWN)

Modify `cancel_task()` method:
- Change status to `FAILED` instead of `CANCELLED`

**File: `backend/api/tasks.py`**

Modify `retry_task()` endpoint:
- Change condition from checking `[FAILED, FAILED_QUOTA]` to just `FAILED`

**File: `backend/main.py`**

Add status migration on startup (after database initialization):
```python
async def migrate_old_statuses():
    async with async_session_maker() as db:
        from sqlalchemy import update
        result = await db.execute(
            update(Task)
            .where(Task.status.in_(['FAILED_QUOTA', 'CANCELLED']))
            .values(status=TaskStatus.FAILED)
        )
        await db.commit()
        if result.rowcount > 0:
            logger.info(f"Migrated {result.rowcount} tasks to FAILED status")

# Call after init_db()
await migrate_old_statuses()
```

### Frontend Changes

**File: `frontend/lib/types.ts`**
- Modify `TaskStatus` enum:
  - Remove `FAILED_QUOTA = 'FAILED_QUOTA'`
  - Remove `CANCELLED = 'CANCELLED'`
  - Keep only: `TODO`, `RUNNING`, `DONE`, `FAILED`

**File: `frontend/components/TaskBoard.tsx`**

Update status columns configuration:
- Change `statusColumns` array from 6 columns to 4 columns
- Remove entries for `FAILED_QUOTA` and `CANCELLED`
- Keep: TODO (slate), RUNNING (blue), DONE (green), FAILED (red)

Update layout:
- Change grid from `lg:grid-cols-6` to `lg:grid-cols-4`

Update grouping function:
- Remove FAILED_QUOTA and CANCELLED from `groupTasksByStatus()` result

---

## Phase 3: Improve Task Board Spacing

### File: `frontend/components/TaskBoard.tsx`

**Increase gap between task cards:**
- Line ~56: Change `space-y-3` to `space-y-5` in the column content div
- This increases vertical spacing from 12px to 20px

### File: `frontend/components/TaskCard.tsx`

**Reduce internal padding:**
- Line ~38: Add `py-3` class to Card component to reduce vertical padding
- Line ~40: Change CardHeader `pb-3` to `pb-2`
- Line ~50: Change CardContent `space-y-2` to `space-y-1`
- Line ~50: Add `pt-0` to CardContent to remove top padding

Result: More breathing room between cards, less wasted space inside each card.

---

## Phase 4: Implement Git Worktree for All Tasks

### Database Schema Changes

**File: `backend/models.py`**

Add to `Task` model (after line ~58):
```python
branch_name = Column(String(200), nullable=True)  # Base branch for worktree
worktree_path = Column(String(1000), nullable=True)  # Path to task's worktree
```

### Backend Schema Updates

**File: `backend/schemas.py`**

Update `TaskBase`:
```python
branch_name: Optional[str] = None
```

Update `TaskResponse`:
```python
branch_name: Optional[str] = None
worktree_path: Optional[str] = None
```

### Git Worktree Implementation

**File: `backend/core/executor.py`**

**Add helper method to detect current branch:**
```python
async def _detect_current_branch(self, workspace_path: str) -> str:
    """Detect the current branch of the workspace."""
    cmd = ["git", "-C", workspace_path, "rev-parse", "--abbrev-ref", "HEAD"]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"Failed to detect branch: {stderr.decode()}")

    return stdout.decode().strip()
```

**Add worktree creation method:**
```python
async def _create_worktree(self, task_id: int, workspace_path: str, base_branch: str) -> str:
    """
    Create a git worktree for the task.

    Returns: Absolute path to the worktree
    """
    worktree_path = f"{workspace_path}-task-{task_id}"
    worktree_branch = f"task-{task_id}"

    # Create worktree with new branch based on user's current branch
    cmd = ["git", "-C", workspace_path, "worktree", "add",
           "-b", worktree_branch, worktree_path, base_branch]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode()
        logger.error(f"Failed to create worktree for task {task_id}: {error_msg}")
        raise RuntimeError(f"Failed to create worktree: {error_msg}")

    logger.info(f"Created worktree at {worktree_path} for task {task_id} from branch {base_branch}")
    return worktree_path
```

**Modify `_execute_task_with_db()` method:**

After line ~60 (after fetching workspace), add:
```python
# Auto-detect base branch if not specified
if not task.branch_name:
    try:
        task.branch_name = await self._detect_current_branch(workspace.path)
        db.add(task)
        await db.commit()
        logger.info(f"Auto-detected base branch '{task.branch_name}' for task {task_id}")
    except Exception as e:
        logger.warning(f"Failed to detect branch for task {task_id}: {e}")
        task.branch_name = "main"  # Fallback to main

# Create worktree for task isolation
try:
    worktree_path = await self._create_worktree(task_id, workspace.path, task.branch_name)
    task.worktree_path = worktree_path
    db.add(task)
    await db.commit()
    actual_workspace = worktree_path
except Exception as e:
    logger.error(f"Failed to create worktree for task {task_id}, using main workspace: {e}")
    actual_workspace = workspace.path
```

Update the call to `_run_task()` to pass `actual_workspace` instead of `workspace.path`.

**Note on cleanup:** Do NOT implement automatic cleanup. Worktrees remain for manual user review and merge.

### Backend API Updates

**File: `backend/api/tasks.py`**

Modify `create_task()` endpoint:
- Accept optional `branch_name` from request body
- If provided, store it in task model
- If not provided, it will be auto-detected during execution

The schema already supports this via `TaskBase.branch_name`.

### Frontend Changes

**File: `frontend/lib/types.ts`**

Update `Task` interface:
```typescript
branch_name?: string;
worktree_path?: string;
```

Update `TaskCreateInput` interface:
```typescript
branch_name?: string;
```

**File: `frontend/components/TaskForm.tsx`**

Add optional branch name field in the form (but it's optional since auto-detect will handle it):

After workspace selection (~line 230), add:
```tsx
<div className="space-y-2">
  <Label htmlFor="branch_name">
    Base Branch (optional)
  </Label>
  <Input
    id="branch_name"
    value={formData.branch_name || ''}
    onChange={(e) =>
      setFormData({ ...formData, branch_name: e.target.value })
    }
    placeholder="Auto-detected if empty"
  />
  <p className="text-xs text-muted-foreground">
    The branch to create the worktree from. Leave empty to auto-detect from workspace.
  </p>
</div>
```

Update state in `useState`:
```typescript
const [formData, setFormData] = useState({
  title: '',
  backend: 'claude_code' as const,
  workspace_id: null as number | null,
  branch_name: '',
});
```

Include `branch_name` in API call when creating task.

---

## Critical Files Summary

### Backend Core Files
- `backend/models.py` - Add worktree fields, remove old statuses
- `backend/core/executor.py` - Implement worktree creation and auto-detection
- `backend/api/tasks.py` - Accept branch_name, update retry logic
- `backend/schemas.py` - Add worktree fields to schemas
- `backend/main.py` - Remove quota/runner routers, add status migration

### Frontend Core Files
- `frontend/components/Navbar.tsx` - Remove quota/runner/usage links
- `frontend/app/layout.tsx` - Remove QuotaAlert component
- `frontend/components/TaskBoard.tsx` - Update status columns (4 instead of 6), improve spacing
- `frontend/components/TaskCard.tsx` - Reduce internal padding
- `frontend/components/TaskForm.tsx` - Add optional branch name field
- `frontend/lib/types.ts` - Update enums and interfaces
- `frontend/lib/api.ts` - Remove quota/runner/usage API calls

---

## Verification Steps

### 1. Verify Quota/Runner Removal
- Navigate to frontend, check navbar only shows: Task Board, New Task, Workspaces
- Try accessing `/quota`, `/runners`, `/usage` URLs - should 404
- No banner alert should appear at top of page
- Backend API should not expose quota/runner/usage endpoints

### 2. Verify Status Consolidation
- Create tasks and let them fail/cancel
- Check Task Board shows only 4 columns: Todo, Running, Done, Failed
- All failed tasks (regardless of reason) should appear in "Failed" column
- Database should have no tasks with FAILED_QUOTA or CANCELLED status

### 3. Verify Spacing Improvements
- Open Task Board with multiple tasks
- Measure vertical spacing between cards (should be ~20px)
- Check internal card padding is reduced (less white space)
- Verify layout looks good on desktop and mobile

### 4. Verify Git Worktree Functionality
- Create a new task without specifying branch name
- Check task execution: confirm worktree is created at `<workspace>-task-<id>`
- Verify new branch `task-<id>` exists
- Check task runs in isolated worktree directory
- After task completion, verify worktree and branch still exist
- Manually inspect worktree changes and test merge workflow
- Try creating task with explicit branch name - should use that branch

### 5. End-to-End Test
- Create task in a git repository workspace
- Task should auto-detect current branch
- Worktree should be created automatically
- Task executes in isolation
- After completion, worktree remains for review
- Check task details show branch_name and worktree_path
- Manually navigate to worktree directory and verify changes
- Test merging worktree branch back to original branch

---

## Implementation Notes

### Error Handling
- If worktree creation fails, task should fail with clear error message
- If branch detection fails, fallback to "main" branch
- Log all git operations for debugging

### Limitations
- Git worktree requires git version 2.5+
- Workspace must be a valid git repository
- Disk space: each worktree is a full working directory

### Future Enhancements (Not in this plan)
- Add cleanup command to remove old worktrees
- Show worktree status in Task details view
- Add merge assistant to help merge completed task branches
- Support SSH/container workspaces with worktrees

---

## Rollback Strategy

If issues occur:
1. Phase 1 (Quota removal): Can re-add deleted files from git history
2. Phase 2 (Status): Run reverse migration to restore old statuses if needed
3. Phase 3 (Spacing): Simple CSS revert
4. Phase 4 (Worktree): Remove worktree fields from DB, remove worktree logic from executor, tasks continue working in main workspace
