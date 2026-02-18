from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
from database import Base


class TaskStatus(str, enum.Enum):
    TODO = "TODO"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class BackendType(str, enum.Enum):
    CLAUDE_CODE = "claude_code"
    CODEX_CLI = "codex_cli"


class RunnerStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class WorkspaceType(str, enum.Enum):
    LOCAL = "local"
    SSH = "ssh"
    SSH_CONTAINER = "ssh_container"


class ErrorClass(str, enum.Enum):
    CODE = "CODE"
    TOOL = "TOOL"
    NETWORK = "NETWORK"
    QUOTA = "QUOTA"
    UNKNOWN = "UNKNOWN"


class QuotaStateValue(str, enum.Enum):
    OK = "OK"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    UNKNOWN = "UNKNOWN"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    prompt = Column(Text, nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.workspace_id"), nullable=False)
    backend = Column(SQLEnum(BackendType), nullable=False)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.TODO, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    run_id = Column(Integer, ForeignKey("runs.run_id"), nullable=True)
    branch_name = Column(String(200), nullable=True)
    worktree_path = Column(String(1000), nullable=True)

    # Relationships
    workspace = relationship("Workspace", back_populates="tasks")
    # runs: all runs for this task (one-to-many)
    runs = relationship("Run", back_populates="task", foreign_keys="[Run.task_id]")
    # run: current/latest run (many-to-one via run_id)
    run = relationship("Run", foreign_keys=[run_id], post_update=True, uselist=False)


class Workspace(Base):
    __tablename__ = "workspaces"

    workspace_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    path = Column(String(1000), nullable=False, unique=True)
    display_name = Column(String(200), nullable=False)
    workspace_type = Column(
        SQLEnum(
            WorkspaceType,
            values_callable=lambda enum_cls: [enum_item.value for enum_item in enum_cls],
            name="workspace_type_enum",
        ),
        default=WorkspaceType.LOCAL,
        nullable=False,
    )
    host = Column(String(255), nullable=True)
    port = Column(Integer, nullable=True)
    ssh_user = Column(String(100), nullable=True)
    container_name = Column(String(200), nullable=True)
    runner_id = Column(Integer, ForeignKey("runners.runner_id"), nullable=False)
    concurrency_limit = Column(Integer, default=1, nullable=False)  # M1: fixed to 1

    # Relationships
    runner = relationship("Runner", back_populates="workspaces")
    tasks = relationship("Task", back_populates="workspace")


class Runner(Base):
    __tablename__ = "runners"

    runner_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    env = Column(String(100), nullable=False)
    capabilities = Column(JSON, nullable=False)  # List of supported backends
    heartbeat_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    status = Column(SQLEnum(RunnerStatus), default=RunnerStatus.ONLINE, nullable=False)
    max_parallel = Column(Integer, default=1, nullable=False)  # M1: fixed to 1

    # Relationships
    workspaces = relationship("Workspace", back_populates="runner")
    runs = relationship("Run", back_populates="runner")


class Run(Base):
    __tablename__ = "runs"

    run_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    runner_id = Column(Integer, ForeignKey("runners.runner_id"), nullable=False)
    backend = Column(String(50), nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    ended_at = Column(DateTime, nullable=True)
    exit_code = Column(Integer, nullable=True)
    error_class = Column(SQLEnum(ErrorClass), nullable=True)
    log_blob = Column(Text, nullable=True)  # M1: store as text
    usage_json = Column(Text, nullable=True)  # M3: usage metrics JSON
    tmux_session = Column(String(200), nullable=True)  # Feat3: tmux session name for SSH workspaces

    # Relationships
    task = relationship("Task", back_populates="runs", foreign_keys=[task_id])
    runner = relationship("Runner", back_populates="runs")


class QuotaState(Base):
    __tablename__ = "quota_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False)  # "claude" or "openai"
    account_label = Column(String(100), nullable=False, default="default")
    state = Column(
        SQLEnum(
            QuotaStateValue,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="quota_state_enum",
        ),
        default=QuotaStateValue.OK,
        nullable=False,
    )
    last_event_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)
