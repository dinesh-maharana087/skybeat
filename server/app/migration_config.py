"""Resolve the dedicated Alembic account without loading application policy."""

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from app.config import DatabaseSettings

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_migration_database_settings(*, root: Path = REPOSITORY_ROOT) -> DatabaseSettings:
    """Process settings override the canonical root .env; runtime URL is never a fallback."""
    values = dotenv_values(root / ".env", interpolate=False)
    migration_url = os.environ.get("SKYBEAT_MIGRATION_DATABASE_URL")
    if migration_url is None:
        migration_url = values.get("SKYBEAT_MIGRATION_DATABASE_URL")
    if not migration_url:
        raise RuntimeError(
            "SKYBEAT_MIGRATION_DATABASE_URL is required for Alembic. "
            "Set it in the process environment or the repository root .env."
        )

    options: dict[str, Any] = {"database_url": migration_url}
    for name in DatabaseSettings.model_fields:
        if name == "database_url":
            continue
        key = f"SKYBEAT_{name.upper()}"
        value = values.get(key)
        if key not in os.environ and value is not None:
            options[name] = value
    return DatabaseSettings(**options)
