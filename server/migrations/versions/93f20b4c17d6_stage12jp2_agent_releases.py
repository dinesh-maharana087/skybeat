"""Record verified agent artifacts and one active installation release.

Revision ID: 93f20b4c17d6
Revises: 4ab92d1e7c30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "93f20b4c17d6"
down_revision: str | None = "4ab92d1e7c30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_releases",
        sa.Column("archive_sha256", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("wheel_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("registered_by", sa.String(128), nullable=False),
        sa.Column("registered_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("verified_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.UniqueConstraint("version", name="uq_agent_releases_version"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_table(
        "agent_release_selection",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("archive_sha256", sa.String(64), nullable=True),
        sa.Column("activated_by", sa.String(128), nullable=True),
        sa.Column("activated_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.ForeignKeyConstraint(
            ["archive_sha256"], ["agent_releases.archive_sha256"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("id = 1", name="singleton"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.execute("INSERT INTO agent_release_selection (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("agent_release_selection")
    op.drop_table("agent_releases")
