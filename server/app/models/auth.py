"""Opaque dashboard sessions and short-lived OAuth transaction records."""

from datetime import datetime

from sqlalchemy import Index, LargeBinary, String
from sqlalchemy.dialects.mysql import BIGINT, BINARY, DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.models import TABLE_OPTIONS, Base


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
