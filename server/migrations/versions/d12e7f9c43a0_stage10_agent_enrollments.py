"""stage10 durable agent enrollment authorizations

Revision ID: d12e7f9c43a0
Revises: b31d2ef4a1c9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "d12e7f9c43a0"
down_revision: str | None = "b31d2ef4a1c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }
    op.create_table(
        "agent_enrollments",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column(
            "public_id",
            mysql.CHAR(length=36, charset="ascii", collation="ascii_bin"),
            nullable=False,
        ),
        sa.Column("enrollment_digest", mysql.BINARY(length=32), nullable=False),
        sa.Column("verification_digest", mysql.BINARY(length=32), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("project_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("replacement_device_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("issued_device_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("device_name", sa.String(length=128), nullable=True),
        sa.Column("gpu_monitoring_enabled", sa.Boolean(), nullable=True),
        sa.Column("expected_gpu_min_count", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("used_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("verification_expires_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint("mode IN ('NEW', 'REPLACE')", name="mode"),
        sa.CheckConstraint(
            "(mode = 'NEW' AND project_id IS NOT NULL AND replacement_device_id IS NULL "
            "AND device_name IS NOT NULL AND gpu_monitoring_enabled IS NOT NULL "
            "AND expected_gpu_min_count IS NOT NULL) OR "
            "(mode = 'REPLACE' AND project_id IS NULL AND replacement_device_id IS NOT NULL "
            "AND device_name IS NULL AND gpu_monitoring_enabled IS NULL "
            "AND expected_gpu_min_count IS NULL)",
            name="target",
        ),
        sa.CheckConstraint(
            "expected_gpu_min_count IS NULL OR expected_gpu_min_count BETWEEN 0 AND 64",
            name="gpu_count",
        ),
        sa.CheckConstraint("used_at IS NULL OR used_at >= created_at", name="used_after_create"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["replacement_device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["issued_device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
        sa.UniqueConstraint("enrollment_digest"),
        sa.UniqueConstraint("verification_digest"),
        **options,
    )
    op.create_index("ix_agent_enrollments_expiry", "agent_enrollments", ["expires_at"])
    op.create_index("ix_agent_enrollments_project_id", "agent_enrollments", ["project_id"])
    op.create_index(
        "ix_agent_enrollments_replacement_device_id",
        "agent_enrollments",
        ["replacement_device_id"],
    )
    op.create_index(
        "ix_agent_enrollments_issued_device_id", "agent_enrollments", ["issued_device_id"]
    )
    op.create_index(
        "ix_agent_enrollments_verification_expiry",
        "agent_enrollments",
        ["verification_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_enrollments_verification_expiry", table_name="agent_enrollments")
    op.drop_index("ix_agent_enrollments_issued_device_id", table_name="agent_enrollments")
    op.drop_index("ix_agent_enrollments_replacement_device_id", table_name="agent_enrollments")
    op.drop_index("ix_agent_enrollments_project_id", table_name="agent_enrollments")
    op.drop_index("ix_agent_enrollments_expiry", table_name="agent_enrollments")
    op.drop_table("agent_enrollments")
