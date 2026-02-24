from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from models import TaskStatus, BackendType, RunnerStatus, ErrorClass, WorkspaceType, QuotaStateValue
from config import settings


# Task Schemas
class TaskBase(BaseModel):
    title: str = Field(..., max_length=500)
    prompt: str = Field(..., max_length=settings.prompt_max_chars)
    workspace_id: int
    backend: BackendType
    branch_name: Optional[str] = Field(None, max_length=200)
    model: Optional[str] = None
    permission_mode: Optional[str] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    run_id: Optional[int] = None


class TaskResponse(TaskBase):
    id: int
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    run_id: Optional[int] = None
    worktree_path: Optional[str] = None
    run_started_at: Optional[datetime] = None
    usage_json: Optional[str] = None
    prompt_history: Optional[List[str]] = None

    @classmethod
    def from_orm(cls, obj):
        instance = super().from_orm(obj)
        try:
            if obj.run is not None:
                instance.run_started_at = obj.run.started_at
                instance.usage_json = obj.run.usage_json
        except Exception:
            pass
        return instance

    class Config:
        orm_mode = True


# Workspace Schemas
class WorkspaceBase(BaseModel):
    path: str = Field(..., max_length=1000)
    display_name: str = Field(..., max_length=200)
    workspace_type: WorkspaceType = WorkspaceType.LOCAL
    host: Optional[str] = Field(None, max_length=255)
    port: Optional[int] = Field(22, ge=1, le=65535)
    ssh_user: Optional[str] = Field(None, max_length=100)
    container_name: Optional[str] = Field(None, max_length=200)


class WorkspaceCreate(WorkspaceBase):
    runner_id: Optional[int] = None


class WorkspaceResponse(WorkspaceBase):
    workspace_id: int
    runner_id: int
    concurrency_limit: int

    class Config:
        orm_mode = True


# Runner Schemas
class RunnerBase(BaseModel):
    env: str
    capabilities: List[str]


class RunnerCreate(RunnerBase):
    pass


class RunnerResponse(RunnerBase):
    runner_id: int
    status: RunnerStatus
    heartbeat_at: datetime
    max_parallel: int

    class Config:
        orm_mode = True


# Run Schemas
class RunBase(BaseModel):
    task_id: int
    runner_id: int
    backend: str


class RunCreate(RunBase):
    pass


class RunUpdate(BaseModel):
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_class: Optional[ErrorClass] = None
    log_blob: Optional[str] = None


class RunResponse(RunBase):
    run_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    error_class: Optional[ErrorClass] = None
    usage_json: Optional[str] = None

    class Config:
        orm_mode = True


# Log Stream Event
class LogEvent(BaseModel):
    run_id: int
    timestamp: datetime
    content: str


# Quota Schemas
class QuotaStateResponse(BaseModel):
    id: int
    provider: str
    account_label: str
    state: QuotaStateValue
    last_event_at: Optional[datetime] = None
    note: Optional[str] = None

    class Config:
        orm_mode = True


class NextTaskNumberResponse(BaseModel):
    next_number: int
    suggested_title: str


class TaskPatch(BaseModel):
    title: Optional[str] = Field(None, max_length=500)


class TaskContinueRequest(BaseModel):
    prompt: str = Field(..., max_length=settings.prompt_max_chars)
    model: Optional[str] = None


# Workspace Resource Monitoring Schemas
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


class AppSettingsResponse(BaseModel):
    workspace_max_parallel: int


class AppSettingsUpdate(BaseModel):
    workspace_max_parallel: int = Field(..., ge=1, le=20)


class WorkspaceHealthResponse(BaseModel):
    reachable: bool
    is_git: bool
    message: str
