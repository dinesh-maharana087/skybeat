"""Read-only, bounded dashboard projections from the authoritative MySQL records."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select

from app.db import Database, database_utc
from app.models import (
    AlertEvent,
    Device,
    DeviceLatest,
    Incident,
    NotificationDelivery,
    Project,
)


class DashboardNotFound(ValueError):
    """Requested dashboard device does not exist."""


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _state(device: Device) -> str:
    if device.last_seen_at is None:
        return "AWAITING_FIRST_HEARTBEAT"
    return device.availability_state


def device_view(
    device: Device, project: Project, latest: DeviceLatest | None, server_time: datetime
) -> dict[str, object]:
    """Build a JSON-safe current view without inventing missing telemetry."""
    state = _state(device)
    telemetry_stale = latest is not None and state != "ONLINE"
    if latest is None:
        return {
            "device_id": device.device_uuid,
            "project": {"project_id": project.public_id, "name": project.name},
            "name": device.name,
            "hostname": None,
            "ip_addresses": [],
            "monitoring_enabled": device.monitoring_enabled,
            "state": state,
            "pending_first_heartbeat": device.last_seen_at is None,
            "last_seen_at": _timestamp(device.last_seen_at),
            "telemetry_stale": False,
            "agent_version": None,
            "uptime_seconds": None,
            "cpu": None,
            "memory": None,
            "disks": [],
            "gpu_health": {
                "reported": None,
                "effective": "NOT MONITORED" if not device.gpu_monitoring_enabled else "UNKNOWN",
            },
            "gpus": [],
        }
    payload = _mapping(latest.payload)
    gpu_health = _mapping(payload.get("gpu_health"))
    effective_gpu_health = (
        "NOT MONITORED" if not device.gpu_monitoring_enabled else gpu_health.get("state", "UNKNOWN")
    )
    return {
        "device_id": device.device_uuid,
        "project": {"project_id": project.public_id, "name": project.name},
        "name": device.name,
        "hostname": latest.hostname,
        "ip_addresses": _list(payload.get("ip_addresses")),
        "monitoring_enabled": device.monitoring_enabled,
        "state": state,
        "pending_first_heartbeat": False,
        "last_seen_at": _timestamp(device.last_seen_at),
        "telemetry_stale": telemetry_stale,
        "agent_version": latest.agent_version,
        "uptime_seconds": payload.get("uptime_seconds"),
        "cpu": {"utilization_percent": latest.cpu_percent},
        "memory": _mapping(payload.get("memory")),
        "disks": _list(payload.get("disks")),
        "gpu_health": {"reported": gpu_health.get("state"), "effective": effective_gpu_health},
        "gpus": _list(payload.get("gpus")),
        "os": _mapping(payload.get("os")),
        "received_at": _timestamp(latest.received_at),
        "collected_at": _timestamp(latest.collected_at),
        "expected_gpu_policy": {
            "minimum_count": device.expected_gpu_min_count,
            "uuids": device.expected_gpu_uuids,
        },
        "server_time": _timestamp(server_time),
    }


class DashboardReadService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_projects(self) -> dict[str, object]:
        with self.database.transaction() as session:
            now = database_utc(session)
            projects = session.scalars(
                select(Project).order_by(Project.name, Project.public_id)
            ).all()
            devices = session.scalars(select(Device)).all()
            by_project: dict[int, list[Device]] = {}
            for device in devices:
                by_project.setdefault(device.project_id, []).append(device)
            items = []
            for project in projects:
                counts = {
                    "total": 0,
                    "online": 0,
                    "suspect": 0,
                    "offline": 0,
                    "awaiting_first_heartbeat": 0,
                }
                for device in by_project.get(project.id, []):
                    counts["total"] += 1
                    state = _state(device).lower()
                    counts[state] += 1
                items.append(
                    {
                        "project_id": project.public_id,
                        "name": project.name,
                        "description": project.description,
                        "is_active": project.is_active,
                        "device_counts": counts,
                    }
                )
            return {"items": items, "server_time": _timestamp(now)}

    def list_devices(
        self,
        *,
        project_id: str | None = None,
        state: str | None = None,
        include_disabled: bool = False,
        search: str | None = None,
        limit: int = 50,
    ) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit is outside the supported range.")
        if state not in {None, "ONLINE", "SUSPECT", "OFFLINE", "AWAITING_FIRST_HEARTBEAT"}:
            raise ValueError("State is invalid.")
        statement = (
            select(Device, Project, DeviceLatest)
            .join(Project, Device.project_id == Project.id)
            .outerjoin(DeviceLatest, DeviceLatest.device_id == Device.id)
            .order_by(Project.name, Device.name, Device.device_uuid)
            .limit(limit + 1)
        )
        if project_id is not None:
            statement = statement.where(Project.public_id == _uuid(project_id))
        if not include_disabled:
            statement = statement.where(Device.monitoring_enabled.is_(True))
        if state == "AWAITING_FIRST_HEARTBEAT":
            statement = statement.where(Device.last_seen_at.is_(None))
        elif state is not None:
            statement = statement.where(
                Device.last_seen_at.is_not(None), Device.availability_state == state
            )
        if search:
            text = search.strip()
            if len(text) > 128:
                raise ValueError("Search is too long.")
            if text:
                escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                pattern = f"%{escaped}%"
                statement = statement.where(
                    or_(
                        Device.name.like(pattern, escape="\\"),
                        Device.device_uuid.like(pattern, escape="\\"),
                        DeviceLatest.hostname.like(pattern, escape="\\"),
                    )
                )
        with self.database.transaction() as session:
            now = database_utc(session)
            records = session.execute(statement).all()
            has_more = len(records) > limit
            items = [
                device_view(device, project, latest, now)
                for device, project, latest in records[:limit]
            ]
            return {
                "items": items,
                "next_cursor": "more" if has_more else None,
                "server_time": _timestamp(now),
                "worker_healthy": True,
            }

    def get_device(self, device_uuid: str) -> dict[str, object]:
        with self.database.transaction() as session:
            now = database_utc(session)
            result = session.execute(
                select(Device, Project, DeviceLatest)
                .join(Project, Device.project_id == Project.id)
                .outerjoin(DeviceLatest, DeviceLatest.device_id == Device.id)
                .where(Device.device_uuid == _uuid(device_uuid))
            ).one_or_none()
            if result is None:
                raise DashboardNotFound("Device not found.")
            device, project, latest = result
            return device_view(device, project, latest, now)

    def list_alerts(self, device_uuid: str, limit: int = 50) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit is outside the supported range.")
        with self.database.transaction() as session:
            now = database_utc(session)
            device = session.scalar(select(Device).where(Device.device_uuid == _uuid(device_uuid)))
            if device is None:
                raise DashboardNotFound("Device not found.")
            events = session.execute(
                select(AlertEvent, Incident)
                .join(Incident, AlertEvent.incident_id == Incident.id)
                .where(AlertEvent.device_id == device.id)
                .order_by(AlertEvent.occurred_at.desc(), AlertEvent.id.desc())
                .limit(limit)
            ).all()
            event_ids = [event.id for event, _ in events]
            deliveries = (
                session.scalars(
                    select(NotificationDelivery).where(NotificationDelivery.event_id.in_(event_ids))
                ).all()
                if event_ids
                else []
            )
            by_event: dict[int, list[dict[str, object]]] = {}
            for delivery in deliveries:
                by_event.setdefault(delivery.event_id, []).append(
                    {
                        "channel": delivery.channel,
                        "status": delivery.status,
                        "attempt_count": delivery.attempt_count,
                        "last_error_code": delivery.last_error_category,
                    }
                )
            items = [
                {
                    "event_id": event.event_uuid,
                    "incident_id": incident.incident_uuid,
                    "type": event.event_kind,
                    "occurred_at": _timestamp(event.occurred_at),
                    "resolved_at": _timestamp(incident.closed_at),
                    "deliveries": by_event.get(event.id, []),
                }
                for event, incident in events
            ]
            return {"items": items, "next_cursor": None, "server_time": _timestamp(now)}


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError):
        raise DashboardNotFound("Device not found.") from None
