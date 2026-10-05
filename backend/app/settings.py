from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str | None = None
    sqlserver_host: str | None = None
    sqlserver_port: int = 1433
    sqlserver_database: str = "ImageProcessing"
    sqlserver_user: str = "sa"
    sqlserver_password: str = ""
    jwt_secret: str = "local-only-secret-change-this-before-sharing"
    jwt_expire_minutes: int = 30
    data_dir: Path = Path("/data")
    max_upload_bytes: int = 20 * 1024 * 1024
    worker_poll_seconds: float = 1.0
    worker_demo_pause_seconds: float = 0
    worker_lease_seconds: int = 60
    worker_heartbeat_seconds: int = 15
    worker_max_attempts: int = 4
    cors_origins: list[str] = ["http://localhost:5173"]

    def sqlalchemy_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        if self.sqlserver_host:
            return URL.create(
                "mssql+pyodbc",
                username=self.sqlserver_user,
                password=self.sqlserver_password,
                host=self.sqlserver_host,
                port=self.sqlserver_port,
                database=self.sqlserver_database,
                query={
                    "driver": "ODBC Driver 18 for SQL Server",
                    "TrustServerCertificate": "yes",
                    "LongAsMax": "Yes",
                },
            )
        return "sqlite+pysqlite:///./image-processing.db"
