"""Bounded per-device Log Watch records and source status.

Revision ID: 2f4a6c8d10b2
Revises: 81be693a0806
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "2f4a6c8d10b2"
down_revision: str | None = "81be693a0806"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "device_log_entries",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("entry_hash", mysql.BINARY(32), nullable=False),
        sa.Column("occurred_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("received_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("message", mysql.TEXT(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "device_id", "source", "entry_hash", name="uq_device_log_entry_source_hash"
        ),
        **_OPTIONS,
    )
    op.create_index(
        "ix_device_log_entries_recent", "device_log_entries", ["device_id", "source", "id"]
    )
    op.create_table(
        "device_log_sources",
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("checked_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("device_id", "source"),
        **_OPTIONS,
    )


def downgrade() -> None:
    op.drop_table("device_log_sources")
    op.drop_index("ix_device_log_entries_recent", table_name="device_log_entries")
    op.drop_table("device_log_entries")
