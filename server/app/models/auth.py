"""Opaque dashboard sessions and short-lived OAuth transaction records."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Computed, Index, LargeBinary, String
from sqlalchemy.dialects.mysql import BIGINT, BINARY, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.models import TABLE_OPTIONS, Base


class ApplicationUser(Base):
    """Durable application authorization identity, separate from Google OIDC sessions."""

    __tablename__ = "application_users"
    __table_args__ = (
        CheckConstraint("role IN ('OWNER', 'ADMIN', 'USER')", name="role"),
        CheckConstraint("owner_guard IS NULL OR owner_guard = 1", name="owner_guard"),
        Index("ix_application_users_role", "role"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean(name="active", create_constraint=True))
    owner_guard: Mapped[int | None] = mapped_column(
        Computed("CASE WHEN role = 'OWNER' THEN 1 ELSE NULL END", persisted=True), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        Index("ix_admin_sessions_expiry", "expires_at"),
        Index("ix_admin_sessions_last_used", "last_used_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    session_hash: Mapped[bytes] = mapped_column(BINARY(32), unique=True)
    google_sub: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320))
    hosted_domain: Mapped[str | None] = mapped_column(String(253))
    issued_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    last_used_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    authorization_policy_version: Mapped[int] = mapped_column(BIGINT(unsigned=True))


class OAuthTransaction(Base):
    __tablename__ = "oauth_transactions"
    __table_args__ = (
        Index("ix_oauth_transactions_expiry", "expires_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    state_hash: Mapped[bytes] = mapped_column(BINARY(32), unique=True)
    nonce_hash: Mapped[bytes] = mapped_column(BINARY(32))
    nonce_ciphertext: Mapped[bytes] = mapped_column(LargeBinary(512))
    browser_binding_hash: Mapped[bytes] = mapped_column(BINARY(32))
    pkce_verifier_ciphertext: Mapped[bytes] = mapped_column(LargeBinary(512))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    consumed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
