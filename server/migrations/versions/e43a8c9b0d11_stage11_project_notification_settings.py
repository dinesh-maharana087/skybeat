"""stage11 project notification settings

Revision ID: e43a8c9b0d11
Revises: d12e7f9c43a0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "e43a8c9b0d11"
down_revision: str | None = "d12e7f9c43a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
    op.create_table(
        "project_notification_settings",
        sa.Column("project_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("device_offline_enabled", sa.Boolean(), nullable=False),
        sa.Column("device_recovered_enabled", sa.Boolean(), nullable=False),
        sa.Column("gpu_degraded_enabled", sa.Boolean(), nullable=False),
        sa.Column("gpu_recovered_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id"),
        **options,
    )
    op.create_table(
        "project_notification_recipients",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("project_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "email", name="uq_project_notification_recipients_project_email"),
        **options,
    )


def downgrade() -> None:
    op.drop_table("project_notification_recipients")
    op.drop_table("project_notification_settings")
