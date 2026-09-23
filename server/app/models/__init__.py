"""Stage 01 identities. UUIDs are external identifiers; integer keys stay internal."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, LargeBinary, MetaData, String
from sqlalchemy.dialects.mysql import BIGINT, BINARY, CHAR, DATETIME, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TABLE_OPTIONS: dict[str, str] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (TABLE_OPTIONS,)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), unique=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(
        Boolean(name="active", create_constraint=True), default=True
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("expected_gpu_min_count BETWEEN 0 AND 64", name="gpu_count"),
        CheckConstraint(
            "JSON_TYPE(expected_gpu_uuids) = 'ARRAY' AND JSON_LENGTH(expected_gpu_uuids) <= 64",
            name="gpu_inventory",
        ),
        CheckConstraint(
            "gpu_monitoring_enabled OR (expected_gpu_min_count = 0 AND "
            "JSON_LENGTH(expected_gpu_uuids) = 0)",
            name="disabled_gpu_policy",
        ),
        CheckConstraint("availability_state IN ('ONLINE', 'SUSPECT', 'OFFLINE')", name="state"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    device_uuid: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), unique=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    monitoring_enabled: Mapped[bool] = mapped_column(
        Boolean(name="monitoring", create_constraint=True)
    )
    monitoring_started_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    last_seen_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    availability_state: Mapped[str] = mapped_column(String(16), default="ONLINE")
    gpu_monitoring_enabled: Mapped[bool] = mapped_column(
        Boolean(name="gpu_monitoring", create_constraint=True)
    )
    expected_gpu_min_count: Mapped[int] = mapped_column(BIGINT(unsigned=True))
    expected_gpu_uuids: Mapped[list[str]] = mapped_column(JSON)
    gpu_effective_state: Mapped[str] = mapped_column(String(32), default="OK")
    gpu_failure_streak: Mapped[int] = mapped_column(BIGINT(unsigned=True), default=0)
    gpu_ok_streak: Mapped[int] = mapped_column(BIGINT(unsigned=True), default=0)
    gpu_last_sample_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))


class DeviceCredential(Base):
    __tablename__ = "device_credentials"
    __table_args__ = (
        Index("ix_credentials_device_lifecycle", "device_id", "revoked_at", "expires_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    credential_id: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), unique=True
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))
    token_digest: Mapped[bytes] = mapped_column(BINARY(32))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    last_used_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (TABLE_OPTIONS,)

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON)


class HeartbeatReceipt(Base):
    __tablename__ = "heartbeat_receipts"
    __table_args__ = (
        Index("ix_heartbeat_receipts_expires_at", "expires_at"),
        TABLE_OPTIONS,
    )

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), primary_key=True
    )
    heartbeat_id: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), primary_key=True
    )
    payload_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    received_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class HeartbeatSample(Base):
    __tablename__ = "heartbeat_samples"
    __table_args__ = (
        Index("ix_heartbeat_samples_device_received", "device_id", "received_at"),
        Index("ix_heartbeat_samples_received_at", "received_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))
    heartbeat_id: Mapped[str] = mapped_column(CHAR(36, charset="ascii", collation="ascii_bin"))
    received_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    collected_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    schema_version: Mapped[int] = mapped_column(BIGINT(unsigned=True))
    agent_version: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DeviceLatest(Base):
    __tablename__ = "device_latest"
    __table_args__ = (TABLE_OPTIONS,)

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), primary_key=True
    )
    heartbeat_id: Mapped[str] = mapped_column(CHAR(36, charset="ascii", collation="ascii_bin"))
    received_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    collected_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    schema_version: Mapped[int] = mapped_column(BIGINT(unsigned=True))
    agent_version: Mapped[str] = mapped_column(String(64))
    hostname: Mapped[str] = mapped_column(String(253))
    primary_ip: Mapped[str | None] = mapped_column(String(45))
    cpu_percent: Mapped[float | None] = mapped_column()
    memory_percent: Mapped[float | None] = mapped_column()
    disk_summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    gpu_summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


from app.models.alerts import (  # noqa: E402
    AlertEvent,
    Incident,
    NotificationAttempt,
    NotificationDelivery,
)
from app.models.auth import AdminSession, OAuthTransaction  # noqa: E402

__all__ = [
    "AlertEvent",
    "AdminSession",
    "AuditEvent",
    "Base",
    "Device",
    "DeviceCredential",
    "DeviceLatest",
    "HeartbeatReceipt",
    "HeartbeatSample",
    "Incident",
    "NotificationAttempt",
    "NotificationDelivery",
    "OAuthTransaction",
    "Project",
]
