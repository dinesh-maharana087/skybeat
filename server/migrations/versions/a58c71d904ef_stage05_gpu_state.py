"""stage05 GPU confirmation state

Revision ID: a58c71d904ef
Revises: 7d2e8a91c4bf
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "a58c71d904ef"
down_revision: str | None = "7d2e8a91c4bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("gpu_effective_state", sa.String(32), server_default="OK", nullable=False),
    )
    op.add_column(
        "devices",
        sa.Column(
            "gpu_failure_streak", mysql.BIGINT(unsigned=True), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "devices",
        sa.Column("gpu_ok_streak", mysql.BIGINT(unsigned=True), server_default="0", nullable=False),
    )
    op.add_column("devices", sa.Column("gpu_last_sample_at", mysql.DATETIME(fsp=6), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "gpu_last_sample_at")
    op.drop_column("devices", "gpu_ok_streak")
    op.drop_column("devices", "gpu_failure_streak")
    op.drop_column("devices", "gpu_effective_state")
