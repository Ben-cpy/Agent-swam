from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
import logging
import sys
import os
from sqlalchemy import text

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    try:
        import codecs
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except (AttributeError, TypeError):
        pass  # Already wrapped or incompatible
    # Set environment variable for subprocess
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from config import settings
from database import init_db, close_db, async_session_maker
from runner.agent import LocalRunnerAgent
from core.scheduler import TaskScheduler, RunnerHeartbeat
from api import tasks, workspaces, logs, usage, terminal, settings as settings_api
from api import ai_models as models_api

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup and shutdown events
    # Startup
    # logger.info(Starting AI Task Manager backend...)

    # Initialize database
    await init_db()

    async with async_session_maker() as db:
        result = await db.execute(
            text(
                "UPDATE tasks SET status = 'FAILED' "
                "WHERE status IN ('FAILED_QUOTA', 'CANCELLED')"
            )
        )
        await db.commit()
        migrated = result.rowcount or 0
        if migrated > 0:
            logger.info(f"Migrated {migrated} tasks from legacy statuses to FAILED")

    # Register local runner
    async with async_session_maker() as db:
        await LocalRunnerAgent.register_local_runner(db)

    # Start scheduler and heartbeat
    scheduler = TaskScheduler(async_session_maker)
    heartbeat = RunnerHeartbeat(async_session_maker)

    await scheduler.start()
    await heartbeat.start()

    # Store in app state for access in routes
    app.state.scheduler = scheduler
    app.state.heartbeat = heartbeat

    logger.info(f"Server ready on http://{settings.api_host}:{settings.api_port}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await scheduler.stop()
    await heartbeat.stop()
    await close_db()


# Create FastAPI app
app = FastAPI(
    title="AI Task Manager API",
    description="Backend API for managing AI tasks with Claude Code and Codex CLI",
    version="1.0.0-M3",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tasks.router)
app.include_router(workspaces.router)
app.include_router(logs.router)
app.include_router(models_api.router)
app.include_router(usage.router)
app.include_router(terminal.router)
app.include_router(settings_api.router)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "message": "AI Task Manager API",
        "version": "1.0.0-M3"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,  # Disable in production
        log_level=settings.log_level.lower()
    )
