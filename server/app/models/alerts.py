"""Durable availability incidents, alert events, and notification queue records."""

from datetime import datetime

from sqlalchemy import CheckConstraint, Computed, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT, CHAR, DATETIME, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models import TABLE_OPTIONS, Base


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("incident_type IN ('AVAILABILITY', 'GPU')", name="type"),
        UniqueConstraint("active_key", name="active_key"),
        Index("ix_incidents_device_type_closed", "device_id", "incident_type", "closed_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    incident_uuid: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), unique=True
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))
    incident_type: Mapped[str] = mapped_column(String(32))
    opened_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    detected_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    closed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    close_reason: Mapped[str | None] = mapped_column(String(64))
    current_reason: Mapped[str | None] = mapped_column(String(64))
    active_key: Mapped[str | None] = mapped_column(
        String(128),
        Computed(
            "CASE WHEN closed_at IS NULL THEN CONCAT(device_id, ':', incident_type) ELSE NULL END",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        CheckConstraint(
            "event_kind IN ('DEVICE_OFFLINE', 'DEVICE_RECOVERED', 'GPU_DEGRADED', 'GPU_RECOVERED')",
            name="kind",
        ),
        UniqueConstraint("incident_id", "event_kind", name="incident_kind"),
        Index("ix_alert_events_device_occurred", "device_id", "occurred_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    event_uuid: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), unique=True
    )
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="RESTRICT"))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="RESTRICT"))
    event_kind: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    detected_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    project_name_snapshot: Mapped[str] = mapped_column(String(128))
    device_name_snapshot: Mapped[str] = mapped_column(String(128))
    reason_snapshot: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        CheckConstraint("channel IN ('EMAIL', 'SMS')", name="channel"),
        CheckConstraint(
            "status IN ('PENDING', 'IN_PROGRESS', 'RETRY_WAIT', "
            "'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="status",
        ),
        UniqueConstraint("event_id", "channel", "recipient_key", name="event_channel_recipient"),
        Index("ix_notification_deliveries_due", "status", "next_attempt_at"),
        Index("ix_notification_deliveries_lease", "status", "lease_expires_at"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    delivery_uuid: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), unique=True
    )
    event_id: Mapped[int] = mapped_column(ForeignKey("alert_events.id", ondelete="RESTRICT"))
    channel: Mapped[str] = mapped_column(String(16))
    recipient_key: Mapped[str] = mapped_column(String(64))
    destination_snapshot: Mapped[str] = mapped_column(String(320))
    provider_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    attempt_count: Mapped[int] = mapped_column(BIGINT(unsigned=True), default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    lease_token: Mapped[str | None] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin")
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    superseded_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    last_error_category: Mapped[str | None] = mapped_column(String(64))
    provider_message_id: Mapped[str | None] = mapped_column(String(256))
    cancel_reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"
    __table_args__ = (
        UniqueConstraint("delivery_id", "attempt_no", name="delivery_attempt"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    delivery_id: Mapped[int] = mapped_column(
        ForeignKey("notification_deliveries.id", ondelete="RESTRICT")
    )
    attempt_no: Mapped[int] = mapped_column(BIGINT(unsigned=True))
    started_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6))
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    outcome: Mapped[str | None] = mapped_column(String(32))
    error_category: Mapped[str | None] = mapped_column(String(64))
    provider_message_id: Mapped[str | None] = mapped_column(String(256))
