"""Deterministic incident-time diagnostics preview for the existing device Log Watch."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.dashboard.read import DashboardNotFound
from app.db import Database
from app.heartbeats.service import wire_time
from app.logs.service import LogWatchService
from app.models import Device, Incident

BEFORE_INCIDENT = timedelta(minutes=5)
AFTER_INCIDENT = timedelta(minutes=10)
CORRELATED_LOG_LIMIT = 50


def _canonical_uuid(value: str) -> str:
    try:
        canonical = str(UUID(value))
    except (TypeError, ValueError):
        raise DashboardNotFound("Incident or device not found.") from None
    if canonical != value:
        raise DashboardNotFound("Incident or device not found.")
    return canonical


class IncidentDiagnosticService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(
        self, device_uuid: str, incident_uuid: str, *, point: str = "opened"
    ) -> dict[str, object]:
        if point not in {"opened", "recovered"}:
            raise ValueError("Incident correlation point is invalid.")
        device_uuid = _canonical_uuid(device_uuid)
        incident_uuid = _canonical_uuid(incident_uuid)
        with self.database.transaction() as session:
            row = session.execute(
                select(Incident, Device)
                .join(Device, Incident.device_id == Device.id)
                .where(
                    Incident.incident_uuid == incident_uuid,
                    Device.device_uuid == device_uuid,
                )
            ).one_or_none()
            if row is None:
                raise DashboardNotFound("Incident or device not found.")
            incident, device = row
            if device.device_uuid != device_uuid:
                raise DashboardNotFound("Incident or device not found.")
            opened_at: datetime = incident.opened_at
            closed_at: datetime | None = incident.closed_at
            incident_type: str = incident.incident_type
        if point == "recovered":
            if closed_at is None:
                raise ValueError("Active incident has no recovery time.")
            anchor = closed_at
        else:
            anchor = opened_at
        start = anchor - BEFORE_INCIDENT
        end = anchor + AFTER_INCIDENT
        nearby = LogWatchService(self.database).near(
            device_uuid, anchor=anchor, start=start, end=end, limit=CORRELATED_LOG_LIMIT
        )
        return {
            "incident": {
                "incident_id": incident_uuid,
                "device_id": device_uuid,
                "type": incident_type,
                "opened_at": wire_time(opened_at),
                "closed_at": wire_time(closed_at) if closed_at else None,
                "point": point,
                "anchor_at": wire_time(anchor),
            },
            "window_start": wire_time(start),
            "window_end": wire_time(end),
            "diagnostics": nearby["items"],
            "truncated": nearby["truncated"],
        }
