"""Server-authoritative availability transitions and durable alert creation."""

import re
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Database, database_utc
from app.gpu.service import GPUIncidentService
from app.models import AlertEvent, Device, Incident, NotificationDelivery, Project


class AvailabilityState(StrEnum):
    ONLINE = "ONLINE"
    SUSPECT = "SUSPECT"
    OFFLINE = "OFFLINE"


SUSPECT_AFTER_SECONDS = 75
OFFLINE_AFTER_SECONDS = 180
NOTIFICATION_EXPIRY = timedelta(hours=24)
_EMAIL_RECIPIENT = re.compile(r"[^\s@\r\n]{1,64}@[^\s@\r\n]{1,255}")


def availability_state(baseline: datetime, now: datetime) -> AvailabilityState:
    """Return the state derived from trusted UTC server timestamps."""
    age_seconds = (now - baseline).total_seconds()
    if age_seconds < SUSPECT_AFTER_SECONDS:
        return AvailabilityState.ONLINE
    if age_seconds < OFFLINE_AFTER_SECONDS:
        return AvailabilityState.SUSPECT
    return AvailabilityState.OFFLINE


def monitoring_baseline(monitoring_started_at: datetime, last_seen_at: datetime | None) -> datetime:
    """Use the latest trusted monitoring-period timestamp, never agent-provided time."""
    return last_seen_at or monitoring_started_at


def validate_email_recipient(value: str) -> str:
    """Accept only a bounded address with no header-injection characters."""
    normalized = value.strip().lower()
    if not _EMAIL_RECIPIENT.fullmatch(normalized):
        raise ValueError("Email recipient is invalid.")
    return normalized


class AvailabilityService:
    """Serializes device availability with the same row lock used by heartbeat ingestion."""

    def __init__(
        self,
        database: Database,
        *,
        email_recipients: tuple[str, ...] = (),
        sms_recipients: tuple[str, ...] = (),
    ) -> None:
        self.database = database
        self.email_recipients = tuple(
            sorted({validate_email_recipient(value) for value in email_recipients})
        )
        self.sms_recipients = tuple(sorted(set(sms_recipients)))

    def sweep(self) -> None:
        """Evaluate every enabled device; the initial fleet is small enough for bounded scans."""
        with self.database.transaction() as session:
            device_ids = session.scalars(
                select(Device.id).where(Device.monitoring_enabled.is_(True))
            ).all()
        for device_id in device_ids:
            self.evaluate_device(device_id)

    def evaluate_device(self, device_id: int) -> None:
        with self.database.transaction() as session:
            device = session.scalar(select(Device).where(Device.id == device_id).with_for_update())
            if device is None or not device.monitoring_enabled:
                return
            now = database_utc(session)
            desired = availability_state(
                monitoring_baseline(device.monitoring_started_at, device.last_seen_at), now
            )
            if desired is AvailabilityState.OFFLINE:
                device.availability_state = AvailabilityState.OFFLINE.value
                self._ensure_offline_incident(session, device, now)
                GPUIncidentService.reset_for_device_offline(session, device, now)
            elif device.availability_state != AvailabilityState.OFFLINE.value:
                device.availability_state = desired.value
            device.updated_at = now

    def accept_heartbeat(self, session: Session, device: Device, received_at: datetime) -> None:
        """Reconcile overdue state before a new accepted heartbeat replaces its baseline."""
        prior_state = availability_state(
            monitoring_baseline(device.monitoring_started_at, device.last_seen_at), received_at
        )
        if prior_state is AvailabilityState.OFFLINE:
            device.availability_state = AvailabilityState.OFFLINE.value
            self._ensure_offline_incident(session, device, received_at)
            GPUIncidentService.reset_for_device_offline(session, device, received_at)
        device.last_seen_at = received_at
        if device.availability_state == AvailabilityState.OFFLINE.value:
            self._close_for_recovery(session, device, received_at)
        else:
            device.availability_state = AvailabilityState.ONLINE.value
        device.updated_at = received_at

    def _active_incident(self, session: Session, device_id: int) -> Incident | None:
        return session.scalar(
            select(Incident).where(
                Incident.device_id == device_id,
                Incident.incident_type == "AVAILABILITY",
                Incident.closed_at.is_(None),
            )
        )

    def _ensure_offline_incident(self, session: Session, device: Device, now: datetime) -> Incident:
        incident = self._active_incident(session, device.id)
        if incident is not None:
            return incident
        incident = Incident(
            incident_uuid=str(uuid4()),
            device_id=device.id,
            incident_type="AVAILABILITY",
            opened_at=now,
            detected_at=now,
            closed_at=None,
            close_reason=None,
            current_reason="heartbeat_timeout",
            created_at=now,
            updated_at=now,
        )
        session.add(incident)
        session.flush()
        self._create_event(session, incident, device, "DEVICE_OFFLINE", now)
        return incident

    def _close_for_recovery(self, session: Session, device: Device, now: datetime) -> None:
        incident = self._active_incident(session, device.id)
        if incident is None:
            device.availability_state = AvailabilityState.ONLINE.value
            return
        incident.closed_at = now
        incident.close_reason = "heartbeat_received"
        incident.current_reason = None
        incident.updated_at = now
        for delivery in session.scalars(
            select(NotificationDelivery)
            .join(AlertEvent, NotificationDelivery.event_id == AlertEvent.id)
            .where(
                AlertEvent.incident_id == incident.id,
                AlertEvent.event_kind == "DEVICE_OFFLINE",
                NotificationDelivery.status.in_(("PENDING", "RETRY_WAIT", "IN_PROGRESS")),
            )
        ):
            delivery.cancel_reason = "superseded_by_recovery"
            delivery.superseded_at = now
            delivery.updated_at = now
            if delivery.status in {"PENDING", "RETRY_WAIT"}:
                delivery.status = "CANCELLED"
                delivery.next_attempt_at = None
        self._create_event(session, incident, device, "DEVICE_RECOVERED", now)
        device.availability_state = AvailabilityState.ONLINE.value

    def _create_event(
        self,
        session: Session,
        incident: Incident,
        device: Device,
        kind: str,
        now: datetime,
    ) -> AlertEvent:
        project = session.get(Project, device.project_id)
        if project is None:
            raise RuntimeError("Device project is missing.")
        event = AlertEvent(
            event_uuid=str(uuid4()),
            incident_id=incident.id,
            device_id=device.id,
            event_kind=kind,
            occurred_at=now,
            detected_at=now,
            project_name_snapshot=project.name,
            device_name_snapshot=device.name,
            reason_snapshot=incident.current_reason,
            details={"availability_state": device.availability_state},
            created_at=now,
        )
        session.add(event)
        session.flush()
        recipients = tuple(("EMAIL", "smtp", value) for value in self.email_recipients) + tuple(
            ("SMS", "sms", value) for value in self.sms_recipients
        )
        for channel, provider, destination in recipients:
            session.add(
                NotificationDelivery(
                    delivery_uuid=str(uuid4()),
                    event_id=event.id,
                    channel=channel,
                    recipient_key=sha256(destination.encode("utf-8")).hexdigest(),
                    destination_snapshot=destination,
                    provider_name=provider,
                    status="PENDING",
                    attempt_count=0,
                    next_attempt_at=now,
                    expires_at=now + NOTIFICATION_EXPIRY,
                    lease_token=None,
                    lease_expires_at=None,
                    superseded_at=None,
                    last_error_category=None,
                    provider_message_id=None,
                    cancel_reason=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        return event
