"""Repair missing lifecycle failure detail without altering history.

Revision ID: d8a71f2c4e30
Revises: 93f20b4c17d6
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import context, op

revision: str = "d8a71f2c4e30"
down_revision: str | None = "93f20b4c17d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_nullable_varchar_64(column: dict[str, Any]) -> bool:
    column_type = column.get("type")
    return (
        isinstance(column_type, sa.String)
        and column_type.length == 64
        and column.get("nullable") is True
    )


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "This reflective schema repair cannot generate offline SQL; run it online "
            "against an operator-confirmed database."
        )
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("device_agent_lifecycle"):
        raise RuntimeError(
            "Cannot repair lifecycle schema: device_agent_lifecycle is missing. "
            "Investigate the database before retrying this migration."
        )
    columns = {column["name"]: column for column in inspector.get_columns("device_agent_lifecycle")}
    existing = columns.get("failure_detail")
    if existing is None:
        op.add_column(
            "device_agent_lifecycle",
            sa.Column("failure_detail", sa.String(64), nullable=True),
        )
        return
    if not _is_nullable_varchar_64(existing):
        raise RuntimeError(
            "Cannot repair lifecycle schema: device_agent_lifecycle.failure_detail "
            "must be VARCHAR(64) NULL. Investigate the database before retrying this migration."
        )


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade is intentionally unsupported because dropping failure_detail could lose "
        "lifecycle data."
    )
