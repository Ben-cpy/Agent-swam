import asyncio
import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import event
from sqlalchemy import text
from config import settings

Base = declarative_base()

logger = logging.getLogger(__name__)

engine_kwargs = {}
if settings.database_url.startswith("sqlite"):
    # Avoid immediate "database is locked" failures under concurrent writes.
    engine_kwargs["connect_args"] = {"timeout": 30}

engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    future=True,
    **engine_kwargs,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            # WAL allows readers and a writer to coexist, critical for SSE polling.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()

async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    # Keep ORM attributes available after commit for FastAPI serialization
    # and post-commit cleanup paths (avoids async MissingGreenlet regressions).
    expire_on_commit=False
)


async def get_db():
    """Dependency for FastAPI routes to get a database session."""
    session = async_session_maker()
    try:
        yield session
    finally:
        if session.in_transaction():
            try:
                await asyncio.shield(session.rollback())
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Session rollback failed during cleanup", exc_info=True)

        try:
            await asyncio.shield(session.close())
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("Session close failed during cleanup", exc_info=True)


async def _migrate_tasks_backend_constraint(conn) -> None:
    """
    Recreate the tasks table to extend the backend CHECK constraint with copilot_cli.
    SQLite does not support ALTER TABLE to change constraints, so a full table recreation
    is needed on existing databases.
    """
    import logging
    logger = logging.getLogger(__name__)

    ddl_row = await conn.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'")
    )
    tasks_ddl = (ddl_row.scalar() or "").lower()

    # Only migrate if there's a CHECK constraint that doesn't include copilot_cli yet
    needs_migration = (
        "copilot_cli" not in tasks_ddl
        and ("claude_code" in tasks_ddl or "codex_cli" in tasks_ddl)
    )
    if not needs_migration:
        return

    logger.info("Migrating tasks table: adding copilot_cli to backend constraint…")
    await conn.execute(text("PRAGMA foreign_keys=OFF"))
    await conn.execute(text("ALTER TABLE tasks RENAME TO _tasks_v1_backup"))
    await conn.execute(text("""
        CREATE TABLE tasks (
            id INTEGER NOT NULL,
            title VARCHAR(500) NOT NULL,
            prompt TEXT NOT NULL,
            workspace_id INTEGER NOT NULL,
            backend VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            run_id INTEGER,
            branch_name VARCHAR(200),
            worktree_path VARCHAR(1000),
            model VARCHAR(200),
            permission_mode VARCHAR(50),
            PRIMARY KEY (id),
            CHECK (backend IN ('claude_code', 'codex_cli', 'copilot_cli')),
            CHECK (status IN ('TODO', 'RUNNING', 'TO_BE_REVIEW', 'DONE', 'FAILED')),
            FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id),
            FOREIGN KEY(run_id) REFERENCES runs(run_id)
        )
    """))
    await conn.execute(text("""
        INSERT INTO tasks
        SELECT id, title, prompt, workspace_id, backend, status,
               created_at, updated_at, run_id,
               branch_name, worktree_path, model, permission_mode
        FROM _tasks_v1_backup
    """))
    await conn.execute(text("DROP TABLE _tasks_v1_backup"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_id ON tasks (id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks (status)"))
    await conn.execute(text("PRAGMA foreign_keys=ON"))
    logger.info("tasks table migration complete")


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            # Extend backend CHECK constraint to include copilot_cli on existing DBs
            await _migrate_tasks_backend_constraint(conn)
            result_tasks = await conn.execute(text("PRAGMA table_info(tasks)"))
            task_columns = {row[1] for row in result_tasks.fetchall()}
            if "branch_name" not in task_columns:
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN branch_name VARCHAR(200)"))
            if "worktree_path" not in task_columns:
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN worktree_path VARCHAR(1000)"))
            if "model" not in task_columns:
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN model VARCHAR(200)"))
            if "permission_mode" not in task_columns:
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN permission_mode VARCHAR(50)"))
            if "prompt_history" not in task_columns:
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN prompt_history JSON"))

            result = await conn.execute(text("PRAGMA table_info(workspaces)"))
            existing_columns = {row[1] for row in result.fetchall()}

            migration_sql = []
            if "workspace_type" not in existing_columns:
                migration_sql.append(
                    "ALTER TABLE workspaces ADD COLUMN workspace_type VARCHAR(30) NOT NULL DEFAULT 'local'"
                )
            if "host" not in existing_columns:
                migration_sql.append("ALTER TABLE workspaces ADD COLUMN host VARCHAR(255)")
            if "port" not in existing_columns:
                migration_sql.append("ALTER TABLE workspaces ADD COLUMN port INTEGER")
            if "ssh_user" not in existing_columns:
                migration_sql.append("ALTER TABLE workspaces ADD COLUMN ssh_user VARCHAR(100)")
            if "container_name" not in existing_columns:
                migration_sql.append("ALTER TABLE workspaces ADD COLUMN container_name VARCHAR(200)")

            for stmt in migration_sql:
                await conn.execute(text(stmt))

            # Normalize legacy enum literals if they were stored as enum names.
            await conn.execute(text("UPDATE workspaces SET workspace_type='local' WHERE workspace_type='LOCAL'"))
            await conn.execute(text("UPDATE workspaces SET workspace_type='ssh' WHERE workspace_type='SSH'"))
            await conn.execute(
                text("UPDATE workspaces SET workspace_type='ssh_container' WHERE workspace_type='SSH_CONTAINER'")
            )

            # M3: Add usage_json column to runs table
            result_runs = await conn.execute(text("PRAGMA table_info(runs)"))
            run_columns = {row[1] for row in result_runs.fetchall()}
            if "usage_json" not in run_columns:
                await conn.execute(text("ALTER TABLE runs ADD COLUMN usage_json TEXT"))
            # Feat3: Add tmux_session column to runs table
            if "tmux_session" not in run_columns:
                await conn.execute(text("ALTER TABLE runs ADD COLUMN tmux_session VARCHAR(200)"))

            setting_row = await conn.execute(
                text("SELECT value FROM app_settings WHERE key = 'workspace_max_parallel' LIMIT 1")
            )
            setting = setting_row.fetchone()
            if setting is None:
                await conn.execute(
                    text(
                        "INSERT INTO app_settings (key, value, updated_at) "
                        "VALUES ('workspace_max_parallel', '3', CURRENT_TIMESTAMP)"
                    )
                )
                await conn.execute(text("UPDATE workspaces SET concurrency_limit = 3"))
                await conn.execute(text("UPDATE runners SET max_parallel = 3"))
    print("Database initialized")


async def close_db():
    """Close database connections"""
    await engine.dispose()
