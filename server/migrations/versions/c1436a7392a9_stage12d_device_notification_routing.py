"""Stage 12D durable device-level notification overrides.

Revision ID: c1436a7392a9
Revises: 2f4a6c8d10b2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "c1436a7392a9"
down_revision: str | None = "2f4a6c8d10b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }
    op.create_table(
        "device_notification_settings",
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("device_offline_enabled", sa.Boolean(), nullable=False),
        sa.Column("device_recovered_enabled", sa.Boolean(), nullable=False),
        sa.Column("gpu_degraded_enabled", sa.Boolean(), nullable=False),
        sa.Column("gpu_recovered_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("device_id"),
        **options,
    )
    op.create_table(
        "device_notification_recipients",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"], ["device_notification_settings.device_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "device_id", "email", name="uq_device_notification_recipients_device_email"
        ),
        **options,
    )


def downgrade() -> None:
    op.drop_table("device_notification_recipients")
    op.drop_table("device_notification_settings")
