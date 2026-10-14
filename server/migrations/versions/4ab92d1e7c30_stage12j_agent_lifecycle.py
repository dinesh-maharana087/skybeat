"""Store one durable lifecycle operation slot per device.

Revision ID: 4ab92d1e7c30
Revises: 5a12e1c0d9f4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "4ab92d1e7c30"
down_revision: str | None = "5a12e1c0d9f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_agent_lifecycle",
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "operation_uuid", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("target_version", sa.String(64), nullable=False),
        sa.Column("target_wheel_sha256", sa.String(64), nullable=False),
        sa.Column("archive_sha256", sa.String(64), nullable=True),
        sa.Column("previous_version", sa.String(64), nullable=True),
        sa.Column("previous_wheel_sha256", sa.String(64), nullable=True),
        sa.Column("rollback_available", sa.Boolean(), nullable=False),
        sa.Column("requester", sa.String(128), nullable=False),
        sa.Column("failure_category", sa.String(32), nullable=True),
        sa.Column("failure_detail", sa.String(64), nullable=True),
        sa.Column("requested_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("device_id"),
        sa.UniqueConstraint("operation_uuid"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade() -> None:
    op.drop_table("device_agent_lifecycle")
