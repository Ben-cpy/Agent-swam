from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from models import Task, Workspace, Runner, TaskStatus, RunnerStatus
from core.executor import TaskExecutor
from datetime import datetime, timedelta
from config import settings
import asyncio
import logging

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Task scheduler that periodically checks for TODO tasks and dispatches them to executors.

    M1 Implementation:
    - Runs every N seconds (configurable)
    - Enforces serial execution per workspace (concurrency_limit = 1)
    - Checks runner availability
    - Simple FIFO scheduling
    """

    def __init__(self, db_session_maker):
        self.db_session_maker = db_session_maker
        self.running = False
        self.scheduler_task = None

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
        1. Workspace has no RUNNING tasks (serial constraint)
        2. Runner is ONLINE
        3. Runner supports the task's backend

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

        # Check if workspace has any RUNNING tasks
        result = await db.execute(
            select(Task)
            .where(and_(
                Task.workspace_id == workspace.workspace_id,
                Task.status == TaskStatus.RUNNING
            ))
        )
        running_tasks = result.scalars().all()

        if running_tasks:
            logger.debug(f"Workspace {workspace.workspace_id} has {len(running_tasks)} running tasks, skipping")
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
        if task.backend.value not in runner.capabilities:
            logger.warning(f"Runner {runner.runner_id} does not support backend {task.backend}")
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

            for runner in runners:
                runner.heartbeat_at = datetime.utcnow()

                # Check if runner is offline (no heartbeat in 2x interval)
                threshold = datetime.utcnow() - timedelta(seconds=settings.heartbeat_interval * 2)
                if runner.heartbeat_at < threshold:
                    runner.status = RunnerStatus.OFFLINE
                else:
                    runner.status = RunnerStatus.ONLINE

            await db.commit()
