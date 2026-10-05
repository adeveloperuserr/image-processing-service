from __future__ import annotations

import re
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

from app.settings import Settings


def ensure_database(settings: Settings, attempts: int = 30, delay_seconds: float = 2) -> None:
    if not settings.sqlserver_host:
        return
    if not re.fullmatch(r"[A-Za-z0-9_]+", settings.sqlserver_database):
        raise ValueError("El nombre de la base de datos solo puede contener letras, números y _.")

    server_url = URL.create(
        "mssql+pyodbc",
        username=settings.sqlserver_user,
        password=settings.sqlserver_password,
        host=settings.sqlserver_host,
        port=settings.sqlserver_port,
        database="master",
        query={
            "driver": "ODBC Driver 18 for SQL Server",
            "TrustServerCertificate": "yes",
        },
    )
    engine = create_engine(server_url, pool_pre_ping=True, connect_args={"timeout": 5})
    try:
        last_error: OperationalError | None = None
        for attempt in range(attempts):
            try:
                with engine.begin() as connection:
                    exists = connection.scalar(
                        text("SELECT DB_ID(:database_name)"),
                        {"database_name": settings.sqlserver_database},
                    )
                    if exists is None:
                        connection.exec_driver_sql(
                            f"CREATE DATABASE [{settings.sqlserver_database}]"
                        )
                return
            except OperationalError as error:
                last_error = error
                if attempt == attempts - 1:
                    raise
                time.sleep(delay_seconds)
        if last_error is not None:
            raise last_error
    finally:
        engine.dispose()


def main() -> None:
    ensure_database(Settings())


if __name__ == "__main__":
    main()
