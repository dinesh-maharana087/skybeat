"""heartbeat storage

Revision ID: 1b2785bb39ef
Revises: 614a53a9e2cb
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "1b2785bb39ef"
down_revision: str | None = "614a53a9e2cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }
    op.create_table(
        "heartbeat_receipts",
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "heartbeat_id", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("payload_hash", sa.LargeBinary(32), nullable=False),
        sa.Column("received_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("response_payload", mysql.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("device_id", "heartbeat_id"),
        **options,
    )
    op.create_index("ix_heartbeat_receipts_expires_at", "heartbeat_receipts", ["expires_at"])
    op.create_table(
        "heartbeat_samples",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "heartbeat_id", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("received_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("collected_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("schema_version", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("agent_version", sa.String(64), nullable=False),
        sa.Column("payload", mysql.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        **options,
    )
    op.create_index(
        "ix_heartbeat_samples_device_received", "heartbeat_samples", ["device_id", "received_at"]
    )
    op.create_index("ix_heartbeat_samples_received_at", "heartbeat_samples", ["received_at"])
    op.create_table(
        "device_latest",
        sa.Column("device_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column(
            "heartbeat_id", mysql.CHAR(36, charset="ascii", collation="ascii_bin"), nullable=False
        ),
        sa.Column("received_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("collected_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("schema_version", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("agent_version", sa.String(64), nullable=False),
        sa.Column("hostname", sa.String(253), nullable=False),
        sa.Column("primary_ip", sa.String(45), nullable=True),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("memory_percent", sa.Float(), nullable=True),
        sa.Column("disk_summary", mysql.JSON(), nullable=False),
        sa.Column("gpu_summary", mysql.JSON(), nullable=False),
        sa.Column("payload", mysql.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("device_id"),
        **options,
    )


def downgrade() -> None:
    op.drop_table("device_latest")
    op.drop_index("ix_heartbeat_samples_received_at", table_name="heartbeat_samples")
    op.drop_index("ix_heartbeat_samples_device_received", table_name="heartbeat_samples")
    op.drop_table("heartbeat_samples")
    op.drop_index("ix_heartbeat_receipts_expires_at", table_name="heartbeat_receipts")
    op.drop_table("heartbeat_receipts")
