from pydantic import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./tasks.db"

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Scheduler
    scheduler_interval: int = 5  # seconds
    heartbeat_interval: int = 30  # seconds

    # Runner
    runner_env: str = "local-windows"
    max_parallel: int = 1

    # Logging
    log_level: str = "INFO"
    max_log_size: int = 10 * 1024 * 1024  # 10MB

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
