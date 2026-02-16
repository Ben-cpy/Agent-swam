from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from models import TaskStatus, BackendType, RunnerStatus, ErrorClass


# Task Schemas
class TaskBase(BaseModel):
    title: str = Field(..., max_length=500)
    prompt: str
    workspace_id: int
    backend: BackendType


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

    class Config:
        orm_mode = True


# Workspace Schemas
class WorkspaceBase(BaseModel):
    path: str = Field(..., max_length=1000)
    display_name: str = Field(..., max_length=200)


class WorkspaceCreate(WorkspaceBase):
    runner_id: int


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

    class Config:
        orm_mode = True


# Log Stream Event
class LogEvent(BaseModel):
    run_id: int
    timestamp: datetime
    content: str
