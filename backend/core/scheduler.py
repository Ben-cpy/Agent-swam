from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from models import Task, Workspace, Runner, TaskStatus, RunnerStatus
from core.executor import TaskExecutor
from core.task_reconciler import TaskReconciler
from datetime import datetime, timedelta, timezone
from typing import Optional
from config import settings
import asyncio
import logging

logger = logging.getLogger(__name__)


def _normalize_utc(dt: Optional[datetime]) -> datetime:
    """Normalize sqlite-returned datetimes to timezone-aware UTC."""
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TaskScheduler:
    """
    Task scheduler that periodically checks for TODO tasks and dispatches them to executors.

    M1+ Implementation:
    - Runs every N seconds (configurable)
    - Enforces per-workspace concurrency limits
    - Enforces per-runner parallel limits
    - Checks runner availability
    - Simple FIFO scheduling
    """

    def __init__(self, db_session_maker):
        self.db_session_maker = db_session_maker
        self.running = False
        self.scheduler_task = None
        self._unsupported_backend_logged: set[tuple[int, str]] = set()
        self.reconciler = TaskReconciler(db_session_maker)

    async def start(self):
        """Start the scheduler background task"""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("✓ Scheduler started")

    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.running:
            try:
                await self._schedule_tick()
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)

            # Wait for next tick
            await asyncio.sleep(settings.scheduler_interval)

    async def _schedule_tick(self):
        """
        Single scheduler tick: find TODO tasks and dispatch them if possible.
        """
        async with self.db_session_maker() as db:
            reconciled = await self.reconciler.reconcile_once(db=db)
            if reconciled > 0:
                logger.info("Reconciled %s dangling task(s)", reconciled)

            # Find TODO tasks ordered by creation time
            result = await db.execute(
                select(Task)
                .where(Task.status == TaskStatus.TODO)
                .order_by(Task.created_at.asc())
            )
            todo_tasks = result.scalars().all()

            if not todo_tasks:
                return

            logger.debug(f"Found {len(todo_tasks)} TODO tasks")

            # Try to dispatch each task
            for task in todo_tasks:
                dispatched = await self._try_dispatch_task(db, task)
                if dispatched:
                    logger.info(f"Dispatched task {task.id}")
                else:
                    logger.debug(f"Task {task.id} not ready to dispatch")

    async def _try_dispatch_task(self, db: AsyncSession, task: Task) -> bool:
        """
        Try to dispatch a single task.

        Checks:
        1. Workspace RUNNING count is below workspace concurrency limit
        2. Runner is ONLINE
        3. Runner supports the task's backend
        4. Runner RUNNING count is below runner max_parallel

        Returns:
            bool: True if task was dispatched
        """
        # Fetch workspace
        result = await db.execute(
            select(Workspace).where(Workspace.workspace_id == task.workspace_id)
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            logger.warning(f"Workspace {task.workspace_id} not found for task {task.id}")
            return False

        workspace_limit = max(1, workspace.concurrency_limit or 1)

        # Check workspace RUNNING count against concurrency limit
        result = await db.execute(
            select(func.count(Task.id))
            .where(and_(
                Task.workspace_id == workspace.workspace_id,
                Task.status == TaskStatus.RUNNING
            ))
        )
        running_count = int(result.scalar() or 0)

        if running_count >= workspace_limit:
            logger.debug(
                "Workspace %s reached concurrency limit %s (running=%s), skipping",
                workspace.workspace_id,
                workspace_limit,
                running_count,
            )
            return False

        # Fetch runner
        result = await db.execute(
            select(Runner).where(Runner.runner_id == workspace.runner_id)
        )
        runner = result.scalar_one_or_none()

        if not runner:
            logger.warning(f"Runner {workspace.runner_id} not found")
            return False

        # Check runner status
        if runner.status != RunnerStatus.ONLINE:
            logger.debug(f"Runner {runner.runner_id} is {runner.status}, skipping")
            return False

        # Check runner capabilities
        backend_value = task.backend.value
        if backend_value not in runner.capabilities:
            key = (runner.runner_id, backend_value)
            if key not in self._unsupported_backend_logged:
                logger.warning(
                    "Runner %s does not support backend %s (capabilities=%s)",
                    runner.runner_id,
                    backend_value,
                    runner.capabilities,
                )
                self._unsupported_backend_logged.add(key)
            return False
        self._unsupported_backend_logged.discard((runner.runner_id, backend_value))

        runner_limit = max(1, runner.max_parallel or 1)
        runner_running_result = await db.execute(
            select(func.count(Task.id))
            .select_from(Task)
            .join(Workspace, Workspace.workspace_id == Task.workspace_id)
            .where(
                Workspace.runner_id == runner.runner_id,
                Task.status == TaskStatus.RUNNING,
            )
        )
        runner_running_count = int(runner_running_result.scalar() or 0)
        if runner_running_count >= runner_limit:
            logger.debug(
                "Runner %s reached max_parallel %s (running=%s), skipping",
                runner.runner_id,
                runner_limit,
                runner_running_count,
            )
            return False

        # All checks passed, dispatch task
        executor = TaskExecutor(self.db_session_maker)
        success = await executor.execute_task(task.id, db=db)

        return success


class RunnerHeartbeat:
    """
    Manages runner heartbeat and status updates.

    M1: Local runner only, updates heartbeat periodically.
    """

    def __init__(self, db_session_maker):
        self.db_session_maker = db_session_maker
        self.running = False
        self.heartbeat_task = None

    async def start(self):
        """Start the heartbeat background task"""
        if self.running:
            return

        self.running = True
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("✓ Runner heartbeat started")

    async def stop(self):
        """Stop the heartbeat"""
        self.running = False
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self):
        """Heartbeat loop"""
        while self.running:
            try:
                await self._update_heartbeat()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}", exc_info=True)

            await asyncio.sleep(settings.heartbeat_interval)

    async def _update_heartbeat(self):
        """Update heartbeat for local runner"""
        async with self.db_session_maker() as db:
            # Update all runners (in M1, should be just one)
            result = await db.execute(select(Runner))
            runners = result.scalars().all()

            threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.heartbeat_interval * 2)
            for runner in runners:
                # Check offline BEFORE updating heartbeat_at (only local runner gets updated)
                last_heartbeat_at = _normalize_utc(runner.heartbeat_at)
                if last_heartbeat_at < threshold:
                    runner.status = RunnerStatus.OFFLINE
                else:
                    runner.status = RunnerStatus.ONLINE
                # Only refresh heartbeat for the local runner (remote runners update themselves)
                if runner.env == settings.runner_env:
                    runner.heartbeat_at = datetime.now(timezone.utc)

            await db.commit()
