"""Deterministic GPU confirmation without agent-controlled policy changes."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AlertEvent, Device, Incident, NotificationDelivery, Project

CONFIRMATION_GAP_SECONDS = 75


class GPUEffectiveState(StrEnum):
    OK = "OK"
    GPU_MISSING = "GPU_MISSING"
    NVIDIA_SMI_FAILED = "NVIDIA_SMI_FAILED"
    DRIVER_ERROR = "DRIVER_ERROR"
    UNKNOWN = "UNKNOWN"
    NOT_MONITORED = "NOT_MONITORED"


@dataclass(frozen=True)
class GPUConfirmation:
    state: GPUEffectiveState
    failure_streak: int
    ok_streak: int
    last_sample_at: datetime | None
    event: str | None = None


def evaluate_gpu_observation(
    prior: GPUConfirmation,
    *,
    reported_state: str,
    inventory_reliable: bool,
    gpus: Sequence[Mapping[str, object]],
    expected_min_count: int,
    expected_uuids: Sequence[str],
    observed_at: datetime,
    monitoring_enabled: bool = True,
) -> GPUConfirmation:
    if not monitoring_enabled:
        return GPUConfirmation(GPUEffectiveState.NOT_MONITORED, 0, 0, observed_at)
    observed = _effective_state(
        reported_state, inventory_reliable, gpus, expected_min_count, expected_uuids
    )
    consecutive = (
        prior.last_sample_at is not None
        and (observed_at - prior.last_sample_at).total_seconds() <= CONFIRMATION_GAP_SECONDS
    )
    if observed is GPUEffectiveState.OK:
        ok = (prior.ok_streak + 1) if consecutive else 1
        event = "GPU_RECOVERED" if prior.state is not GPUEffectiveState.OK and ok == 2 else None
        return GPUConfirmation(
            GPUEffectiveState.OK if event else prior.state,
            0,
            ok,
            observed_at,
            event,
        )
    failures = (prior.failure_streak + 1) if consecutive else 1
    event = "GPU_DEGRADED" if prior.state is GPUEffectiveState.OK and failures == 2 else None
    return GPUConfirmation(observed if event else prior.state, failures, 0, observed_at, event)


def _effective_state(
    reported_state: str,
    inventory_reliable: bool,
    gpus: Sequence[Mapping[str, object]],
    expected_min_count: int,
    expected_uuids: Sequence[str],
) -> GPUEffectiveState:
    if reported_state != "OK":
        return GPUEffectiveState(reported_state)
    if not inventory_reliable:
        return GPUEffectiveState.NVIDIA_SMI_FAILED
    observed_uuids = {gpu.get("uuid") for gpu in gpus if isinstance(gpu.get("uuid"), str)}
    if len(gpus) < expected_min_count or not set(expected_uuids).issubset(observed_uuids):
        return GPUEffectiveState.GPU_MISSING
    return GPUEffectiveState.OK


class GPUIncidentService:
    """Persist confirmed aggregate GPU lifecycle transitions in the heartbeat transaction."""

    def __init__(
        self, *, email_recipients: tuple[str, ...] = (), sms_recipients: tuple[str, ...] = ()
    ) -> None:
        self.recipients = tuple(("EMAIL", "smtp", value) for value in email_recipients) + tuple(
            ("SMS", "sms", value) for value in sms_recipients
        )

    def accept(
        self, session: Session, device: Device, payload: Mapping[str, object], now: datetime
    ) -> None:
        health = payload.get("gpu_health")
        gpus = payload.get("gpus")
        if not isinstance(health, Mapping) or not isinstance(gpus, list):
            return
        confirmation = evaluate_gpu_observation(
            GPUConfirmation(
                GPUEffectiveState(device.gpu_effective_state),
                device.gpu_failure_streak,
                device.gpu_ok_streak,
                device.gpu_last_sample_at,
            ),
            reported_state=str(health.get("state")),
            inventory_reliable=health.get("inventory_reliable") is True,
            gpus=[item for item in gpus if isinstance(item, Mapping)],
            expected_min_count=device.expected_gpu_min_count,
            expected_uuids=device.expected_gpu_uuids,
            observed_at=now,
            monitoring_enabled=device.gpu_monitoring_enabled
            and device.availability_state != "OFFLINE",
        )
        device.gpu_effective_state = confirmation.state.value
        device.gpu_failure_streak = confirmation.failure_streak
        device.gpu_ok_streak = confirmation.ok_streak
        device.gpu_last_sample_at = confirmation.last_sample_at
        if confirmation.event == "GPU_DEGRADED":
            self._open(session, device, now, confirmation.state.value, gpus)
        elif confirmation.event == "GPU_RECOVERED":
            self._close(session, device, now)
        elif confirmation.state not in {GPUEffectiveState.OK, GPUEffectiveState.NOT_MONITORED}:
            self._update_current_reason(session, device, confirmation.state.value, now)

    @staticmethod
    def reset_for_device_offline(session: Session, device: Device, now: datetime) -> None:
        """Reset fresh-sample confirmation and supersede undelivered degradation alerts."""
        device.gpu_failure_streak = 0
        device.gpu_ok_streak = 0
        device.gpu_last_sample_at = None
        for delivery in session.scalars(
            select(NotificationDelivery)
            .join(AlertEvent, NotificationDelivery.event_id == AlertEvent.id)
            .join(Incident, AlertEvent.incident_id == Incident.id)
            .where(
                Incident.device_id == device.id,
                Incident.incident_type == "GPU",
                AlertEvent.event_kind == "GPU_DEGRADED",
                NotificationDelivery.status.in_(("PENDING", "RETRY_WAIT", "IN_PROGRESS")),
            )
        ):
            GPUIncidentService._supersede_delivery(delivery, now)

    def _active(self, session: Session, device: Device) -> Incident | None:
        return session.scalar(
            select(Incident).where(
                Incident.device_id == device.id,
                Incident.incident_type == "GPU",
                Incident.closed_at.is_(None),
            )
        )

    def _open(
        self, session: Session, device: Device, now: datetime, reason: str, gpus: object
    ) -> None:
        if self._active(session, device):
            return
        incident = Incident(
            incident_uuid=str(uuid4()),
            device_id=device.id,
            incident_type="GPU",
            opened_at=now,
            detected_at=now,
            closed_at=None,
            close_reason=None,
            current_reason=reason,
            created_at=now,
            updated_at=now,
        )
        session.add(incident)
        session.flush()
        self._event(
            session, incident, device, "GPU_DEGRADED", now, {"reported_state": reason, "gpus": gpus}
        )

    def _update_current_reason(
        self, session: Session, device: Device, reason: str, now: datetime
    ) -> None:
        incident = self._active(session, device)
        if incident is not None:
            incident.current_reason = reason
            incident.updated_at = now

    def _close(self, session: Session, device: Device, now: datetime) -> None:
        incident = self._active(session, device)
        if incident is None:
            return
        incident.closed_at = now
        incident.close_reason = "confirmed_ok"
        incident.current_reason = None
        incident.updated_at = now
        for delivery in session.scalars(
            select(NotificationDelivery)
            .join(AlertEvent, NotificationDelivery.event_id == AlertEvent.id)
            .where(
                AlertEvent.incident_id == incident.id,
                AlertEvent.event_kind == "GPU_DEGRADED",
                NotificationDelivery.status.in_(("PENDING", "RETRY_WAIT", "IN_PROGRESS")),
            )
        ):
            self._supersede_delivery(delivery, now)
        self._event(session, incident, device, "GPU_RECOVERED", now, {"effective_state": "OK"})

    @staticmethod
    def _supersede_delivery(delivery: NotificationDelivery, now: datetime) -> None:
        delivery.cancel_reason = "superseded_by_recovery"
        delivery.superseded_at = now
        delivery.updated_at = now
        if delivery.status in {"PENDING", "RETRY_WAIT"}:
            delivery.status = "CANCELLED"
            delivery.next_attempt_at = None

    def _event(
        self,
        session: Session,
        incident: Incident,
        device: Device,
        kind: str,
        now: datetime,
        details: dict[str, object],
    ) -> None:
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
            details=details,
            created_at=now,
        )
        session.add(event)
        session.flush()
        for channel, provider, destination in self.recipients:
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
                    expires_at=now + timedelta(hours=24),
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
