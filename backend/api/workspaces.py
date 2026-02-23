from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, List, Optional
from pathlib import Path
from database import get_db
from core.settings_service import get_workspace_max_parallel
from models import Workspace, Runner, WorkspaceType, Task, TaskStatus, Run
from schemas import WorkspaceCreate, WorkspaceResponse, WorkspaceResourcesResponse, GpuInfo, MemoryInfo
import asyncio
import os
import platform

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _build_canonical_path(workspace: WorkspaceCreate) -> str:
    if workspace.workspace_type == WorkspaceType.LOCAL:
        return os.path.abspath(os.path.normpath(workspace.path))

    if workspace.workspace_type == WorkspaceType.SSH:
        user_part = f"{workspace.ssh_user}@" if workspace.ssh_user else ""
        port = workspace.port or 22
        return f"ssh://{user_part}{workspace.host}:{port}{workspace.path}"

    user_part = f"{workspace.ssh_user}@" if workspace.ssh_user else ""
    port = workspace.port or 22
    return (
        f"ssh://{user_part}{workspace.host}:{port}"
        f"/container/{workspace.container_name}:{workspace.path}"
    )


def _validate_workspace_input(workspace: WorkspaceCreate):
    if workspace.workspace_type == WorkspaceType.LOCAL:
        if not os.path.exists(workspace.path):
            raise HTTPException(status_code=400, detail="Local workspace path does not exist")
        return

    if not workspace.host:
        raise HTTPException(status_code=400, detail="Host is required for SSH workspace")

    if workspace.workspace_type == WorkspaceType.SSH_CONTAINER and not workspace.container_name:
        raise HTTPException(status_code=400, detail="Container name is required for SSH container workspace")


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    workspace: WorkspaceCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new workspace"""
    _validate_workspace_input(workspace)
    canonical_path = _build_canonical_path(workspace)

    # Check if path already exists
    result = await db.execute(
        select(Workspace).where(Workspace.path == canonical_path)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="Workspace with this path already exists")

    runner = None
    if workspace.runner_id is not None:
        runner_result = await db.execute(
            select(Runner).where(Runner.runner_id == workspace.runner_id)
        )
        runner = runner_result.scalar_one_or_none()
        if not runner:
            raise HTTPException(status_code=400, detail="Runner not found")
    else:
        runner_result = await db.execute(
            select(Runner).order_by(Runner.runner_id.asc())
        )
        runner = runner_result.scalars().first()
        if not runner:
            raise HTTPException(status_code=400, detail="No runner available")

    new_workspace = Workspace(
        path=canonical_path,
        display_name=workspace.display_name,
        workspace_type=workspace.workspace_type,
        host=workspace.host,
        port=workspace.port,
        ssh_user=workspace.ssh_user,
        container_name=workspace.container_name,
        runner_id=runner.runner_id,
        concurrency_limit=await get_workspace_max_parallel(db),
    )

    db.add(new_workspace)
    await db.commit()
    await db.refresh(new_workspace)

    return new_workspace


@router.get("", response_model=List[WorkspaceResponse])
async def list_workspaces(db: AsyncSession = Depends(get_db)):
    """List all workspaces"""
    result = await db.execute(select(Workspace))
    workspaces = result.scalars().all()

    return workspaces


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific workspace by ID"""
    result = await db.execute(
        select(Workspace).where(Workspace.workspace_id == workspace_id)
    )
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return workspace


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a workspace. Rejects if any task is currently RUNNING."""
    ws_result = await db.execute(
        select(Workspace).where(Workspace.workspace_id == workspace_id)
    )
    workspace = ws_result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Guard: reject if any task is RUNNING in this workspace
    running_result = await db.execute(
        select(Task).where(
            Task.workspace_id == workspace_id,
            Task.status == TaskStatus.RUNNING,
        )
    )
    if running_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Cannot delete workspace with running tasks. Cancel them first.",
        )

    # Cascade: delete runs then tasks for this workspace
    tasks_result = await db.execute(
        select(Task).where(Task.workspace_id == workspace_id)
    )
    tasks = tasks_result.scalars().all()
    for task in tasks:
        task.run_id = None
    await db.flush()

    for task in tasks:
        runs_result = await db.execute(
            select(Run).where(Run.task_id == task.id)
        )
        for run in runs_result.scalars().all():
            await db.delete(run)
        await db.delete(task)

    await db.delete(workspace)
    await db.commit()


async def _run_local_command(args: list[str]) -> tuple[int, str]:
    """Run a local subprocess and return (returncode, stdout)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
    return proc.returncode, stdout.decode(errors="replace")


async def _run_ssh_command(ssh_host: str, cmd: str) -> Optional[str]:
    """Run a command on a remote SSH host, returning stdout or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh", ssh_host, f"{cmd} 2>/dev/null || echo UNAVAILABLE",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        text = stdout.decode(errors="replace").strip()
        if text == "UNAVAILABLE" or proc.returncode != 0:
            return None
        return text
    except Exception:
        return None


def _parse_gpu_output(raw: str) -> Optional[List[GpuInfo]]:
    """Parse nvidia-smi CSV output into GpuInfo list."""
    gpus = []
    for line in raw.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            gpus.append(GpuInfo(
                name=parts[0],
                memory_used_mb=int(parts[1]),
                memory_total_mb=int(parts[2]),
                utilization_pct=int(parts[3]),
            ))
        except (ValueError, IndexError):
            continue
    return gpus if gpus else None


def _parse_memory_linux(raw: str) -> Optional[MemoryInfo]:
    """Parse `free -m` output (Linux)."""
    for line in raw.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            if len(parts) >= 4:
                try:
                    total = int(parts[1])
                    used = int(parts[2])
                    free = int(parts[3])
                    used_pct = round(used / total * 100, 1) if total > 0 else 0.0
                    return MemoryInfo(total_mb=total, used_mb=used, free_mb=free, used_pct=used_pct)
                except (ValueError, IndexError):
                    pass
    return None


def _parse_memory_windows(raw: str) -> Optional[MemoryInfo]:
    """Parse wmic output (Windows, values in KB)."""
    values: Dict[str, int] = {}
    for line in raw.splitlines():
        line = line.strip()
        if "=" in line:
            key, _, val = line.partition("=")
            try:
                values[key.strip()] = int(val.strip())
            except ValueError:
                pass
    total_kb = values.get("TotalVisibleMemorySize")
    free_kb = values.get("FreePhysicalMemory")
    if total_kb and free_kb:
        total_mb = total_kb // 1024
        free_mb = free_kb // 1024
        used_mb = total_mb - free_mb
        used_pct = round(used_mb / total_mb * 100, 1) if total_mb > 0 else 0.0
        return MemoryInfo(total_mb=total_mb, used_mb=used_mb, free_mb=free_mb, used_pct=used_pct)
    return None


NVIDIA_SMI_ARGS = [
    "nvidia-smi",
    "--query-gpu=name,memory.used,memory.total,utilization.gpu",
    "--format=csv,noheader,nounits",
]


@router.get("/{workspace_id}/resources", response_model=WorkspaceResourcesResponse)
async def get_workspace_resources(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return GPU and memory usage for the workspace's machine."""
    result = await db.execute(select(Workspace).where(Workspace.workspace_id == workspace_id))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    is_ssh = workspace.workspace_type in (WorkspaceType.SSH, WorkspaceType.SSH_CONTAINER)

    if not is_ssh:
        # --- LOCAL ---
        # GPU
        gpu: Optional[List[GpuInfo]] = None
        gpu_available = False
        try:
            rc, out = await _run_local_command(NVIDIA_SMI_ARGS)
            if rc == 0:
                gpu = _parse_gpu_output(out)
                gpu_available = gpu is not None
        except (FileNotFoundError, asyncio.TimeoutError, OSError):
            gpu_available = False

        # Memory
        memory: Optional[MemoryInfo] = None
        try:
            if platform.system() == "Windows":
                rc, out = await _run_local_command([
                    "wmic", "OS", "get",
                    "FreePhysicalMemory,TotalVisibleMemorySize",
                    "/Value", "/format:list",
                ])
                if rc == 0:
                    memory = _parse_memory_windows(out)
            else:
                rc, out = await _run_local_command(["free", "-m"])
                if rc == 0:
                    memory = _parse_memory_linux(out)
        except (FileNotFoundError, asyncio.TimeoutError, OSError):
            memory = None

        return WorkspaceResourcesResponse(gpu=gpu, gpu_available=gpu_available, memory=memory)

    # --- SSH ---
    ssh_host = workspace.host
    if not ssh_host:
        return WorkspaceResourcesResponse(gpu=None, gpu_available=False, memory=None)

    # GPU via SSH
    gpu = None
    gpu_available = False
    nvidia_cmd = " ".join(NVIDIA_SMI_ARGS)
    gpu_raw = await _run_ssh_command(ssh_host, nvidia_cmd)
    if gpu_raw:
        gpu = _parse_gpu_output(gpu_raw)
        gpu_available = gpu is not None

    # Memory via SSH (assume Linux remote)
    memory = None
    mem_raw = await _run_ssh_command(ssh_host, "free -m")
    if mem_raw:
        memory = _parse_memory_linux(mem_raw)

    return WorkspaceResourcesResponse(gpu=gpu, gpu_available=gpu_available, memory=memory)


# ---------------------------------------------------------------------------
# File listing for @mention autocomplete
# ---------------------------------------------------------------------------

_IGNORE_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", "__pycache__", ".next", "dist", "build",
    ".venv", "venv", "env", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", ".cargo", "vendor", "coverage", ".nyc_output", "tasks",
    ".idea", ".vscode", "out", "tmp", ".turbo",
})


def _fuzzy_score(rel_path: str, query: str) -> int:
    """Return a match score for rel_path vs query (0 = no match, higher = better)."""
    if not query:
        return 1  # return everything when no query

    q = query.lower()
    basename = Path(rel_path).name.lower()
    stem = Path(rel_path).stem.lower()
    path_lc = rel_path.lower()

    if basename == q or stem == q:
        return 1000
    if basename.startswith(q) or stem.startswith(q):
        return 900
    if q in basename:
        return 700
    if q in path_lc:
        return 500

    # Subsequence match in basename (e.g. "tsf" → "TaskForm")
    pi = 0
    for ch in basename:
        if pi < len(q) and ch == q[pi]:
            pi += 1
    if pi == len(q):
        return 300

    # Subsequence match anywhere in path
    pi = 0
    for ch in path_lc:
        if pi < len(q) and ch == q[pi]:
            pi += 1
    if pi == len(q):
        return 100

    return 0


def _list_files_local(root: str, query: str, limit: int) -> list[str]:
    """Walk workspace directory, score files against query, return top matches."""
    base = Path(root)
    scored: list[tuple[int, str]] = []
    try:
        for dirpath, dirnames, filenames in os.walk(base):
            # Prune ignored and hidden directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in _IGNORE_DIRS and not d.startswith(".")
            ]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                try:
                    rel = (Path(dirpath) / fn).relative_to(base).as_posix()
                except ValueError:
                    continue
                sc = _fuzzy_score(rel, query)
                if sc > 0:
                    scored.append((sc, rel))
    except (PermissionError, OSError):
        pass
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [r for _, r in scored[:limit]]


@router.get("/{workspace_id}/files", response_model=List[str])
async def list_workspace_files(
    workspace_id: int,
    query: str = "",
    limit: int = 8,
    task_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return files in a workspace or task worktree matching *query* (fuzzy, case-insensitive).

    Used by the frontend @mention autocomplete in the prompt textarea.
    If task_id is provided, search in the task's worktree instead of the workspace root.
    """
    result = await db.execute(
        select(Workspace).where(Workspace.workspace_id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Determine search path: worktree (if task_id provided) or workspace
    search_path = workspace.path
    if task_id is not None:
        task_result = await db.execute(
            select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
        )
        task = task_result.scalar_one_or_none()
        if task and task.worktree_path:
            search_path = task.worktree_path

    if workspace.workspace_type == WorkspaceType.LOCAL:
        files = await asyncio.to_thread(
            _list_files_local, search_path, query, limit
        )
        return files

    # SSH / SSH_CONTAINER: run find on the remote host
    ssh_host = workspace.host
    find_path = (search_path or "").rstrip("/")
    if not ssh_host or not find_path:
        return []

    cmd = (
        f"find '{find_path}' -maxdepth 10 "
        r"\( -name '.git' -o -name 'node_modules' -o -name '__pycache__'"
        r" -o -name '.next' -o -name 'venv' -o -name '.venv'"
        r" -o -name 'dist' -o -name 'build' -o -name 'target' \) -prune"
        " -o -type f -not -name '.*' -print 2>/dev/null | head -2000"
    )
    raw = await _run_ssh_command(ssh_host, cmd)
    if not raw:
        return []

    scored: list[tuple[int, str]] = []
    for line in raw.strip().splitlines():
        full = line.strip()
        if not full:
            continue
        rel = (
            full[len(find_path):].lstrip("/")
            if full.startswith(find_path)
            else full
        )
        sc = _fuzzy_score(rel, query)
        if sc > 0:
            scored.append((sc, rel))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [r for _, r in scored[:limit]]
