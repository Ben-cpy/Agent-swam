from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import event
from sqlalchemy import text
from config import settings

Base = declarative_base()

engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    future=True
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db():
    """Dependency for FastAPI routes to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
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
    print("Database initialized")


async def close_db():
    """Close database connections"""
    await engine.dispose()
