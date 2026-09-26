"""Opaque dashboard sessions and short-lived OAuth transaction records."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Computed, ForeignKey, Index, LargeBinary, String
from sqlalchemy.dialects.mysql import BIGINT, BINARY, CHAR, DATETIME
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


class AgentEnrollment(Base):
    """A one-time agent enrollment authorization and its verification receipt."""

    __tablename__ = "agent_enrollments"
    __table_args__ = (
        CheckConstraint("mode IN ('NEW', 'REPLACE')", name="mode"),
        CheckConstraint(
            "(mode = 'NEW' AND project_id IS NOT NULL AND replacement_device_id IS NULL "
            "AND device_name IS NOT NULL AND gpu_monitoring_enabled IS NOT NULL "
            "AND expected_gpu_min_count IS NOT NULL) OR "
            "(mode = 'REPLACE' AND project_id IS NULL AND replacement_device_id IS NOT NULL "
            "AND device_name IS NULL AND gpu_monitoring_enabled IS NULL "
            "AND expected_gpu_min_count IS NULL)",
            name="target",
        ),
        CheckConstraint(
            "expected_gpu_min_count IS NULL OR expected_gpu_min_count BETWEEN 0 AND 64",
            name="gpu_count",
        ),
        CheckConstraint("used_at IS NULL OR used_at >= created_at", name="used_after_create"),
        Index("ix_agent_enrollments_expiry", "expires_at"),
        Index("ix_agent_enrollments_verification_expiry", "verification_expires_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), unique=True
    )
    enrollment_digest: Mapped[bytes] = mapped_column(BINARY(32), unique=True)
    verification_digest: Mapped[bytes | None] = mapped_column(BINARY(32), unique=True)
    mode: Mapped[str] = mapped_column(String(16))
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    replacement_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), index=True
    )
    issued_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), index=True
    )
    device_name: Mapped[str | None] = mapped_column(String(128))
    gpu_monitoring_enabled: Mapped[bool | None] = mapped_column(Boolean(create_constraint=True))
    expected_gpu_min_count: Mapped[int | None] = mapped_column(BIGINT(unsigned=True))
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    used_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    verification_expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
