"""stage09 durable application users and sole Owner

Revision ID: b31d2ef4a1c9
Revises: a58c71d904ef
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "b31d2ef4a1c9"
down_revision: str | None = "a58c71d904ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    options = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}
    op.create_table(
        "application_users",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column("google_sub", sa.String(255), nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("owner_guard", mysql.TINYINT(), sa.Computed("CASE WHEN role = 'OWNER' THEN 1 ELSE NULL END", persisted=True), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("role IN ('OWNER', 'ADMIN', 'USER')", name="role"),
        sa.CheckConstraint("owner_guard IS NULL OR owner_guard = 1", name="owner_guard"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"), sa.UniqueConstraint("google_sub"), sa.UniqueConstraint("owner_guard"), **options,
    )
    op.create_index("ix_application_users_role", "application_users", ["role"])


def downgrade() -> None:
    op.drop_index("ix_application_users_role", table_name="application_users")
    op.drop_table("application_users")
