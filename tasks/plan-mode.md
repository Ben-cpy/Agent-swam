# Plan: Plan Mode Support & Workspace Resource Monitoring

## Context
Two independent features:
1. **Plan Mode for Claude Code**: Users can select a `--permission-mode` when creating a task (e.g. `plan` = Claude only plans, does not execute). Currently `--dangerously-skip-permissions` is hardcoded. The new UI shows a mode selector (predefined options + custom input) visible only for the Claude Code backend.
2. **GPU & Memory Monitoring**: The workspace board page shows live GPU (NVIDIA) and RAM usage for the workspace's machine (local or SSH remote). Gracefully shows "unavailable" when hardware is missing.

---

## Feature 1: Plan Mode (Permission Mode) Selection

### Backend

#### 1. `backend/models.py`
Add column to `Task`:
```python
permission_mode = Column(String(50), nullable=True)  # None = bypassPermissions (current default)
```

#### 2. `backend/database.py` — `init_db()`
Add migration in the SQLite migration block:
```python
if "permission_mode" not in task_columns:
    await conn.execute(text("ALTER TABLE tasks ADD COLUMN permission_mode VARCHAR(50)"))
```

#### 3. `backend/schemas.py` — `TaskBase`
```python
permission_mode: Optional[str] = None
```

#### 4. `backend/core/backends/claude_code.py`
Update `ClaudeCodeAdapter`:
```python
def __init__(self, workspace_path, model=None, permission_mode=None):
    ...
    self.permission_mode = permission_mode

def build_command(self, prompt):
    cmd = [resolve_cli("claude"), "-p", "--output-format", "stream-json"]
    mode = self.permission_mode
    if not mode or mode == "bypassPermissions":
        cmd.append("--dangerously-skip-permissions")
    else:
        cmd += ["--permission-mode", mode]
    if self.model:
        cmd += ["--model", self.model]
    cmd.append(prompt)
    return cmd
```

#### 5. `backend/core/executor.py`
- Local path: pass `permission_mode=task.permission_mode` to `ClaudeCodeAdapter()`
- SSH path: add `permission_mode` parameter to `_run_ssh_task()` and update the CLI string:
  ```python
  if not permission_mode or permission_mode == "bypassPermissions":
      perm_flag = "--dangerously-skip-permissions"
  else:
      perm_flag = f"--permission-mode {shlex.quote(permission_mode)}"
  cli_cmd = f"claude -p --output-format stream-json {perm_flag} {shlex.quote(prompt)}"
  ```
- Update the `create_task()` call site to pass `permission_mode=task.permission_mode`

---

### Frontend

#### 6. `frontend/lib/types.ts`
- `Task`: add `permission_mode?: string | null`
- `TaskCreateInput`: add `permission_mode?: string`

#### 7. `frontend/components/TaskForm.tsx`
Add `permission_mode` to `formData`. When `backend === BackendType.CLAUDE_CODE`, show a permission mode selector below the backend field:

- Predefined options in a `<Select>`: `bypassPermissions` (default), `plan`, `acceptEdits`, `dontAsk`, `default`, `Custom...`
- When "Custom..." is selected, reveal an `<Input>` for free text
- Pass `permission_mode` in the `taskAPI.create()` call

---

## Feature 2: GPU & Memory Monitoring

### Backend

#### 8. `backend/schemas.py` — new schemas
```python
class GpuInfo(BaseModel):
    name: str
    memory_used_mb: int
    memory_total_mb: int
    utilization_pct: int

class MemoryInfo(BaseModel):
    total_mb: int
    used_mb: int
    free_mb: int
    used_pct: float

class WorkspaceResourcesResponse(BaseModel):
    gpu: Optional[List[GpuInfo]] = None
    gpu_available: bool
    memory: Optional[MemoryInfo] = None
```

#### 9. `backend/api/workspaces.py` — new endpoint
```
GET /api/workspaces/{workspace_id}/resources
```
Logic:
- **LOCAL**: run commands as local subprocess
  - GPU: `nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits`; handle `FileNotFoundError` → `gpu_available=False`
  - Memory (Windows `platform.system()=="Windows"`): `wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value /format:list` (KB values); Linux: `free -m` (parse first `Mem:` row)
- **SSH / SSH_CONTAINER**: `ssh {workspace.host} "<same commands> 2>/dev/null || echo UNAVAILABLE"`
  - 5-second timeout per command
  - If SSH fails or returns UNAVAILABLE → graceful null
- Returns `WorkspaceResourcesResponse`

No new Python packages needed — uses only `asyncio.create_subprocess_exec` and `platform`.

---

### Frontend

#### 10. `frontend/lib/types.ts` — new types
```typescript
interface GpuInfo { name: string; memory_used_mb: number; memory_total_mb: number; utilization_pct: number; }
interface MemoryInfo { total_mb: number; used_mb: number; free_mb: number; used_pct: number; }
interface WorkspaceResources { gpu: GpuInfo[] | null; gpu_available: boolean; memory: MemoryInfo | null; }
```

#### 11. `frontend/lib/api.ts`
Add to `workspaceAPI`:
```ts
resources: (id: number) => apiClient.get<WorkspaceResources>(`/workspaces/${id}/resources`),
```

#### 12. `frontend/components/WorkspaceResources.tsx` (new file)
Compact panel with two sections:
- **GPU**: if `gpu_available=false` → "GPU: Not available". Otherwise, one row per GPU: name, VRAM used/total, utilization progress bar.
- **Memory**: used/total in GB, used% progress bar.
- Auto-refresh every 10 seconds via `useSWR` with `refreshInterval: 10000`.

#### 13. `frontend/app/workspaces/[id]/board/page.tsx`
Import `WorkspaceResources` and render it between the breadcrumb header and the task board.

---

## Files Modified
| File | Change |
|------|--------|
| `backend/models.py` | Add `permission_mode` column |
| `backend/database.py` | Migration for `permission_mode` |
| `backend/schemas.py` | `TaskBase` field + 3 new resource schemas |
| `backend/core/backends/claude_code.py` | `permission_mode` param in adapter |
| `backend/core/executor.py` | Pass mode to local adapter & SSH command |
| `backend/api/workspaces.py` | New `/resources` endpoint |
| `frontend/lib/types.ts` | `permission_mode` in Task/TaskCreateInput + resource types |
| `frontend/lib/api.ts` | `workspaceAPI.resources()` |
| `frontend/components/TaskForm.tsx` | Permission mode selector UI |
| `frontend/components/WorkspaceResources.tsx` | **New** resource panel component |
| `frontend/app/workspaces/[id]/board/page.tsx` | Add `WorkspaceResources` to board |

---

## Verification
1. Start backend (`uvicorn main:app`) — confirm DB migration adds `permission_mode` column
2. Create a Claude Code task with `permission_mode=plan` → verify command includes `--permission-mode plan` in logs
3. Create task with default mode → verify `--dangerously-skip-permissions` is still used
4. Open workspace board → `WorkspaceResources` panel renders with GPU/memory data (or "Not available" on machines without NVIDIA GPU)
5. For SSH workspaces → resources panel queries remote host correctly
6. Test custom permission mode input in the form
