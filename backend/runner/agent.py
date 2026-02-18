from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models import Runner, RunnerStatus
from datetime import datetime, timezone
from config import settings
import logging

logger = logging.getLogger(__name__)


class LocalRunnerAgent:
    """
    Local runner agent for M1.

    Registers itself in the database on startup and updates heartbeat periodically.
    In M1, the runner runs in the same process as the controller.
    """

    @staticmethod
    async def register_local_runner(db: AsyncSession) -> Runner:
        """
        Register or update the local runner in the database.

        Returns:
            Runner: The registered/updated runner instance
        """
        # Check if local runner already exists
        result = await db.execute(
            select(Runner).where(Runner.env == settings.runner_env)
        )
        runner = result.scalar_one_or_none()

        if runner:
            # Update existing runner
            runner.status = RunnerStatus.ONLINE
            runner.heartbeat_at = datetime.now(timezone.utc)
            runner.capabilities = ["claude_code", "codex_cli"]
            runner.max_parallel = settings.max_parallel
            logger.info(f"✓ Local runner updated (ID: {runner.runner_id})")
        else:
            # Create new runner
            runner = Runner(
                env=settings.runner_env,
                capabilities=["claude_code", "codex_cli"],
                status=RunnerStatus.ONLINE,
                heartbeat_at=datetime.now(timezone.utc),
                max_parallel=settings.max_parallel
            )
            db.add(runner)
            await db.flush()
            logger.info(f"✓ Local runner registered (ID: {runner.runner_id})")

        await db.commit()
        return runner
