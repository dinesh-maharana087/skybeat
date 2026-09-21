"""Bounded MySQL connections and explicit transactional sessions."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_engine(
            settings.database_url.get_secret_value(),
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_pre_ping=True,
            pool_recycle=1800,
            isolation_level="READ COMMITTED",
            hide_parameters=True,
            connect_args={
                "charset": "utf8mb4",
                "connect_timeout": settings.db_connect_timeout_seconds,
                "read_timeout": settings.db_read_timeout_seconds,
                "write_timeout": settings.db_write_timeout_seconds,
            },
        )

        @event.listens_for(self.engine, "connect")
        def initialize_session(connection: Any, record: Any) -> None:
            with connection.cursor() as cursor:
                cursor.execute("SET time_zone = '+00:00'")
                cursor.execute("SET SESSION innodb_lock_wait_timeout = %s", (settings.db_lock_timeout_seconds,))
                cursor.execute("SET SESSION max_execution_time = %s", (settings.db_select_timeout_ms,))
                cursor.execute("SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self.sessions.begin() as session:
            yield session

    def ready(self) -> bool:
        try:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            expected_heads = set(ScriptDirectory.from_config(config).get_heads())
            if not expected_heads:
                return False
            with self.engine.connect() as connection:
                version, timezone, engine, charset = connection.execute(text(
                    "SELECT VERSION(), @@session.time_zone, @@default_storage_engine, @@character_set_connection"
                )).one()
                if (
                    not str(version).startswith("8.")
                    or "mariadb" in str(version).lower()
                    or timezone != "+00:00"
                    or str(engine).lower() != "innodb"
                    or charset != "utf8mb4"
                ):
                    return False
                heads = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
                return heads == expected_heads
        except (SQLAlchemyError, OSError, ValueError):
            logger.warning("Database readiness check failed", extra={"error_category": "database_unavailable"})
            return False

    def dispose(self) -> None:
        self.engine.dispose()


def database_utc(session: Session) -> datetime:
    value = session.execute(text("SELECT UTC_TIMESTAMP(6)")).scalar_one()
    if not isinstance(value, datetime):
        raise RuntimeError("Unexpected database timestamp type.")
    return value
