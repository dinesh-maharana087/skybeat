"""stage04 dashboard authentication

Revision ID: 7d2e8a91c4bf
Revises: 625bfa1677df
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "7d2e8a91c4bf"
down_revision: str | None = "625bfa1677df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }
    op.create_table(
        "admin_sessions",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("session_hash", mysql.BINARY(32), nullable=False),
        sa.Column("google_sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hosted_domain", sa.String(253), nullable=True),
        sa.Column("issued_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_used_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("authorization_policy_version", mysql.BIGINT(unsigned=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_hash"),
        **options,
    )
    op.create_index("ix_admin_sessions_expiry", "admin_sessions", ["expires_at"])
    op.create_index("ix_admin_sessions_last_used", "admin_sessions", ["last_used_at"])
    op.create_table(
        "oauth_transactions",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("state_hash", mysql.BINARY(32), nullable=False),
        sa.Column("nonce_hash", mysql.BINARY(32), nullable=False),
        sa.Column("nonce_ciphertext", sa.LargeBinary(512), nullable=False),
        sa.Column("browser_binding_hash", mysql.BINARY(32), nullable=False),
        sa.Column("pkce_verifier_ciphertext", sa.LargeBinary(512), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("consumed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
        **options,
    )
    op.create_index("ix_oauth_transactions_expiry", "oauth_transactions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_oauth_transactions_expiry", table_name="oauth_transactions")
    op.drop_table("oauth_transactions")
    op.drop_index("ix_admin_sessions_last_used", table_name="admin_sessions")
    op.drop_index("ix_admin_sessions_expiry", table_name="admin_sessions")
    op.drop_table("admin_sessions")
