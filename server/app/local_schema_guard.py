"""Fail local development startup clearly when an explicit migration is pending."""

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import String, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import DatabaseSettings
from app.db import Database


class SchemaMismatch(RuntimeError):
    """The local database cannot safely serve this checkout's schema."""


def require_current_schema(database_heads: set[str], required_heads: set[str]) -> None:
    if len(required_heads) != 1:
        raise SchemaMismatch(
            "SkyBeat source must have exactly one Alembic head before local startup."
        )
    required = next(iter(required_heads))
    if database_heads != required_heads:
        found = ", ".join(sorted(database_heads)) or "none"
        raise SchemaMismatch(
            "SkyBeat database schema does not match the application. "
            f"Database: {found}. Required: {required}. "
            "Review the migration, then run 'python -m alembic upgrade head' from server/."
        )


def require_lifecycle_schema(columns: Sequence[Mapping[str, Any]]) -> None:
    failure_detail = next(
        (column for column in columns if column.get("name") == "failure_detail"), None
    )
    if failure_detail is None:
        raise SchemaMismatch(
            "SkyBeat database lifecycle schema is missing required "
            "device_agent_lifecycle.failure_detail VARCHAR(64) NULL. "
            "Review the migration before local startup."
        )
    column_type = failure_detail.get("type")
    if (
        not isinstance(column_type, String)
        or column_type.length != 64
        or failure_detail.get("nullable") is not True
    ):
        raise SchemaMismatch(
            "SkyBeat database lifecycle schema has an incompatible "
            "device_agent_lifecycle.failure_detail definition; expected VARCHAR(64) NULL. "
            "Review the migration before local startup."
        )


def run() -> None:
    if os.environ.get("SKYBEAT_ENV") != "development":
        raise SchemaMismatch("Local schema guard requires SKYBEAT_ENV=development.")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    required_heads = set(ScriptDirectory.from_config(config).get_heads())
    settings = DatabaseSettings()
    database = Database(settings)
    try:
        with database.engine.connect() as connection:
            current_heads = set(
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
            )
            require_current_schema(current_heads, required_heads)
            require_lifecycle_schema(inspect(connection).get_columns("device_agent_lifecycle"))
    except SQLAlchemyError:
        raise SchemaMismatch(
            "SkyBeat local database or alembic_version is unavailable. "
            "Check the protected database configuration and MySQL service."
        ) from None
    finally:
        database.dispose()


if __name__ == "__main__":
    try:
        run()
    except SchemaMismatch as exc:
        raise SystemExit(str(exc)) from None
