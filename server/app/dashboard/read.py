"""Read-only, bounded dashboard projections from the authoritative MySQL records."""

import base64
import binascii
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select

from app.db import Database, database_utc
from app.models import (
    AlertEvent,
    Device,
    DeviceLatest,
    HeartbeatSample,
    Incident,
    NotificationDelivery,
    Project,
)

CURSOR_MAX_LENGTH = 512
CURSOR_VERSION = 1
HISTORY_RAW_CAP = 5_000
HISTORY_POINT_CAP = 240
HISTORY_GPU_SERIES_CAP = 64
GPU_STATES = {
    "OK",
    "GPU_MISSING",
    "NVIDIA_SMI_FAILED",
    "DRIVER_ERROR",
    "UNKNOWN",
    "NOT_MONITORED",
}
HISTORY_RANGES = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


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


@dataclass(frozen=True)
class DeviceCursor:
    project_name: str
    device_name: str
    device_uuid: str


@dataclass(frozen=True)
class IncidentCursor:
    opened_at: datetime
    incident_id: int


def _cursor_error() -> ValueError:
    return ValueError("Cursor is invalid.")


def _canonical_cursor_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise _cursor_error()
    try:
        canonical = str(UUID(value))
    except ValueError:
        raise _cursor_error() from None
    if canonical != value:
        raise _cursor_error()
    return canonical


def _cursor_text(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise _cursor_error()
    return value


def _encode_cursor(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_cursor(value: str, *, expected_fields: set[str], kind: str) -> dict[str, object]:
    if not isinstance(value, str) or not value or len(value) > CURSOR_MAX_LENGTH:
        raise _cursor_error()
    try:
        raw = value.encode("ascii")
        padded = raw + b"=" * (-len(raw) % 4)
        decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        raise _cursor_error() from None
    if (
        not isinstance(payload, dict)
        or set(payload) != expected_fields
        or payload.get("v") != CURSOR_VERSION
        or payload.get("kind") != kind
    ):
        raise _cursor_error()
    return payload


def encode_device_cursor(cursor: DeviceCursor) -> str:
    return _encode_cursor(
        {
            "v": CURSOR_VERSION,
            "kind": "device",
            "project_name": cursor.project_name,
            "device_name": cursor.device_name,
            "device_uuid": cursor.device_uuid,
        }
    )


def decode_device_cursor(value: str | None) -> DeviceCursor | None:
    if value is None:
        return None
    payload = _decode_cursor(
        value,
        expected_fields={"v", "kind", "project_name", "device_name", "device_uuid"},
        kind="device",
    )
    return DeviceCursor(
        project_name=_cursor_text(payload["project_name"]),
        device_name=_cursor_text(payload["device_name"]),
        device_uuid=_canonical_cursor_uuid(payload["device_uuid"]),
    )


def _cursor_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z") or len(value) > 32:
        raise _cursor_error()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _cursor_error() from None
    if parsed.tzinfo is None:
        raise _cursor_error()
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _cursor_incident_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _cursor_error()
    return value


def encode_incident_cursor(cursor: IncidentCursor) -> str:
    opened_at = _timestamp(cursor.opened_at)
    if opened_at is None:
        raise _cursor_error()
    return _encode_cursor(
        {
            "v": CURSOR_VERSION,
            "kind": "incident",
            "opened_at": opened_at,
            "incident_id": cursor.incident_id,
        }
    )


def decode_incident_cursor(value: str | None) -> IncidentCursor | None:
    if value is None:
        return None
    payload = _decode_cursor(
        value,
        expected_fields={"v", "kind", "opened_at", "incident_id"},
        kind="incident",
    )
    return IncidentCursor(
        opened_at=_cursor_datetime(payload["opened_at"]),
        incident_id=_cursor_incident_id(payload["incident_id"]),
    )


def _metric(value: object) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return value


def _history_sample_points(samples: Sequence[object]) -> list[object]:
    if len(samples) <= HISTORY_POINT_CAP:
        return list(samples)
    buckets = HISTORY_POINT_CAP
    return [
        samples[math.ceil((bucket + 1) * len(samples) / buckets) - 1] for bucket in range(buckets)
    ]


def downsample_history(samples: Sequence[object]) -> dict[str, object]:
    """Project bounded chronological telemetry history without fabricated metrics."""
    selected = _history_sample_points(samples)
    cpu_utilization: list[dict[str, object]] = []
    memory_utilization: list[dict[str, object]] = []
    observations: list[
        tuple[str, str, dict[str, object], float | int | None, float | int | None]
    ] = []
    for sample in selected:
        received_at = getattr(sample, "received_at", None)
        timestamp = _timestamp(received_at if isinstance(received_at, datetime) else None)
        if timestamp is None:
            continue
        payload = _mapping(getattr(sample, "payload", None))
        cpu = _mapping(payload.get("cpu"))
        memory = _mapping(payload.get("memory"))
        cpu_utilization.append(
            {"received_at": timestamp, "value": _metric(cpu.get("utilization_percent"))}
        )
        memory_utilization.append(
            {"received_at": timestamp, "value": _metric(memory.get("utilization_percent"))}
        )
        for raw_gpu in _list(payload.get("gpus")):
            gpu = _mapping(raw_gpu)
            uuid = gpu.get("uuid")
            index = gpu.get("index")
            if isinstance(uuid, str) and uuid:
                series_id = f"uuid:{uuid}"
                identity: dict[str, object] = {"kind": "uuid", "value": uuid}
            elif isinstance(index, int) and not isinstance(index, bool) and index >= 0:
                series_id = f"index:{index}"
                identity = {"kind": "index", "value": index}
            else:
                continue
            observations.append(
                (
                    series_id,
                    timestamp,
                    identity,
                    _metric(gpu.get("utilization_percent")),
                    _metric(gpu.get("temperature_celsius")),
                )
            )
    newest_ids: list[str] = []
    for series_id, _, _, _, _ in reversed(observations):
        if series_id not in newest_ids:
            newest_ids.append(series_id)
        if len(newest_ids) == HISTORY_GPU_SERIES_CAP:
            break
    selected_ids = set(newest_ids)
    all_ids = {series_id for series_id, _, _, _, _ in observations}
    series: dict[str, dict[str, object]] = {}
    for series_id, timestamp, identity, utilization, temperature in observations:
        if series_id not in selected_ids:
            continue
        item = series.setdefault(
            series_id,
            {
                "series_id": series_id,
                "identity": identity,
                "utilization": [],
                "temperature": [],
            },
        )
        utilization_points = item["utilization"]
        temperature_points = item["temperature"]
        if isinstance(utilization_points, list) and isinstance(temperature_points, list):
            utilization_points.append({"received_at": timestamp, "value": utilization})
            temperature_points.append({"received_at": timestamp, "value": temperature})
    return {
        "cpu_utilization": cpu_utilization,
        "memory_utilization": memory_utilization,
        "gpu_series": [series[key] for key in sorted(series)],
        "series_truncated": len(all_ids) > HISTORY_GPU_SERIES_CAP,
    }


def _state(device: Device) -> str:
    if device.last_seen_at is None:
        return "AWAITING_FIRST_HEARTBEAT"
    return device.availability_state


def effective_gpu_state(device: Device) -> str:
    return "NOT_MONITORED" if not device.gpu_monitoring_enabled else device.gpu_effective_state


def _incident_view(incident: Incident, device: Device, project: Project) -> dict[str, object]:
    return {
        "incident_id": incident.incident_uuid,
        "device_id": device.device_uuid,
        "device_name": device.name,
        "project_name": project.name,
        "type": incident.incident_type,
        "reason": incident.current_reason,
        "opened_at": _timestamp(incident.opened_at),
        "closed_at": _timestamp(incident.closed_at),
        "status": "ACTIVE" if incident.closed_at is None else "CLOSED",
        "resolution": incident.close_reason,
    }


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
            "primary_ip": None,
            "ip_addresses": [],
            "monitoring_enabled": device.monitoring_enabled,
            "state": state,
            "pending_first_heartbeat": device.last_seen_at is None,
            "last_seen_at": _timestamp(device.last_seen_at),
            "latest_received_at": None,
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
            "gpu_count": None,
        }
    payload = _mapping(latest.payload)
    gpus_value = payload.get("gpus")
    gpus = _list(gpus_value)
    gpu_health = _mapping(payload.get("gpu_health"))
    effective_gpu_health = effective_gpu_state(device)
    return {
        "device_id": device.device_uuid,
        "project": {"project_id": project.public_id, "name": project.name},
        "name": device.name,
        "hostname": latest.hostname,
        "primary_ip": latest.primary_ip,
        "ip_addresses": _list(payload.get("ip_addresses")),
        "monitoring_enabled": device.monitoring_enabled,
        "state": state,
        "pending_first_heartbeat": False,
        "last_seen_at": _timestamp(device.last_seen_at),
        "latest_received_at": _timestamp(latest.received_at),
        "telemetry_stale": telemetry_stale,
        "agent_version": latest.agent_version,
        "uptime_seconds": payload.get("uptime_seconds"),
        "cpu": {"utilization_percent": latest.cpu_percent},
        "memory": _mapping(payload.get("memory")),
        "disks": _list(payload.get("disks")),
        "gpu_health": {"reported": gpu_health.get("state"), "effective": effective_gpu_health},
        "gpus": gpus,
        "gpu_count": len(gpus) if isinstance(gpus_value, list) else None,
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

    def overview(self) -> dict[str, object]:
        """Return bounded current-state counts using the device-list state projection."""
        with self.database.transaction() as session:
            now = database_utc(session)
            total = int(session.scalar(select(func.count(Device.id))) or 0)
            state_expression = case(
                (Device.last_seen_at.is_(None), "AWAITING_FIRST_HEARTBEAT"),
                else_=Device.availability_state,
            )
            state_rows = session.execute(
                select(state_expression, func.count(Device.id)).group_by(state_expression)
            ).all()
            state_counts = {str(state): int(count) for state, count in state_rows}
            gpu_problem = int(
                session.scalar(
                    select(func.count(Device.id)).where(
                        Device.gpu_monitoring_enabled.is_(True), Device.gpu_effective_state != "OK"
                    )
                )
                or 0
            )
            active_incidents = int(
                session.scalar(select(func.count(Incident.id)).where(Incident.closed_at.is_(None)))
                or 0
            )
            project_rows = session.execute(
                select(
                    Project.public_id,
                    Project.name,
                    func.count(Device.id),
                    func.sum(
                        case(
                            (
                                and_(
                                    Device.last_seen_at.is_not(None),
                                    Device.availability_state == "ONLINE",
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    func.sum(
                        case(
                            (
                                and_(
                                    Device.last_seen_at.is_not(None),
                                    Device.availability_state == "SUSPECT",
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    func.sum(
                        case(
                            (
                                and_(
                                    Device.last_seen_at.is_not(None),
                                    Device.availability_state == "OFFLINE",
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    func.sum(case((Device.last_seen_at.is_(None), 1), else_=0)),
                )
                .outerjoin(Device, Device.project_id == Project.id)
                .group_by(Project.id, Project.public_id, Project.name)
                .order_by(Project.name, Project.public_id)
                .limit(101)
            ).all()
            project_items = []
            for row in project_rows[:100]:
                public_id, name, total_count, online, suspect, offline, awaiting = row
                project_items.append(
                    {
                        "project_id": public_id,
                        "name": name,
                        "device_counts": {
                            "total": int(total_count or 0),
                            "online": int(online or 0),
                            "suspect": int(suspect or 0),
                            "offline": int(offline or 0),
                            "awaiting_first_heartbeat": int(awaiting or 0),
                        },
                    }
                )
            return {
                "counts": {
                    "total": total,
                    "online": state_counts.get("ONLINE", 0),
                    "suspect": state_counts.get("SUSPECT", 0),
                    "offline": state_counts.get("OFFLINE", 0),
                    "awaiting_first_heartbeat": state_counts.get("AWAITING_FIRST_HEARTBEAT", 0),
                    "gpu_problem": gpu_problem,
                    "active_incident": active_incidents,
                },
                "projects": project_items,
                "projects_truncated": len(project_rows) > 100,
                "server_time": _timestamp(now),
            }

    def list_devices(
        self,
        *,
        project_id: str | None = None,
        state: str | None = None,
        include_disabled: bool = False,
        search: str | None = None,
        gpu_state: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit is outside the supported range.")
        if state not in {None, "ONLINE", "SUSPECT", "OFFLINE", "AWAITING_FIRST_HEARTBEAT"}:
            raise ValueError("State is invalid.")
        if gpu_state not in {None, *GPU_STATES}:
            raise ValueError("GPU state is invalid.")
        page_cursor = decode_device_cursor(cursor)
        statement = (
            select(Device, Project, DeviceLatest)
            .join(Project, Device.project_id == Project.id)
            .outerjoin(DeviceLatest, DeviceLatest.device_id == Device.id)
            .order_by(Project.name, Device.name, Device.device_uuid)
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
        if gpu_state == "NOT_MONITORED":
            statement = statement.where(Device.gpu_monitoring_enabled.is_(False))
        elif gpu_state is not None:
            statement = statement.where(
                Device.gpu_monitoring_enabled.is_(True), Device.gpu_effective_state == gpu_state
            )
        if page_cursor is not None:
            statement = statement.where(
                or_(
                    Project.name > page_cursor.project_name,
                    and_(
                        Project.name == page_cursor.project_name,
                        Device.name > page_cursor.device_name,
                    ),
                    and_(
                        Project.name == page_cursor.project_name,
                        Device.name == page_cursor.device_name,
                        Device.device_uuid > page_cursor.device_uuid,
                    ),
                )
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
            records = session.execute(statement.limit(limit + 1)).all()
            has_more = len(records) > limit
            page = records[:limit]
            next_cursor = None
            if has_more and page:
                device, project, _ = page[-1]
                next_cursor = encode_device_cursor(
                    DeviceCursor(project.name, device.name, device.device_uuid)
                )
            items = [device_view(device, project, latest, now) for device, project, latest in page]
            return {
                "items": items,
                "next_cursor": next_cursor,
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

    def list_incidents(self, *, limit: int = 50, cursor: str | None = None) -> dict[str, object]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit is outside the supported range.")
        page_cursor = decode_incident_cursor(cursor)
        statement = (
            select(Incident, Device, Project)
            .join(Device, Incident.device_id == Device.id)
            .join(Project, Device.project_id == Project.id)
            .order_by(Incident.opened_at.desc(), Incident.id.desc())
        )
        if page_cursor is not None:
            statement = statement.where(
                or_(
                    Incident.opened_at < page_cursor.opened_at,
                    and_(
                        Incident.opened_at == page_cursor.opened_at,
                        Incident.id < page_cursor.incident_id,
                    ),
                )
            )
        with self.database.transaction() as session:
            now = database_utc(session)
            rows = session.execute(statement.limit(limit + 1)).all()
            page = rows[:limit]
            next_cursor = None
            if len(rows) > limit and page:
                incident, _, _ = page[-1]
                next_cursor = encode_incident_cursor(
                    IncidentCursor(incident.opened_at, incident.id)
                )
            return {
                "items": [
                    _incident_view(incident, device, project) for incident, device, project in page
                ],
                "next_cursor": next_cursor,
                "server_time": _timestamp(now),
            }

    def device_history(self, device_uuid: str, range_name: str) -> dict[str, object]:
        if range_name not in HISTORY_RANGES:
            raise ValueError("Range is invalid.")
        with self.database.transaction() as session:
            now = database_utc(session)
            device_id = session.scalar(
                select(Device.id).where(Device.device_uuid == _uuid(device_uuid))
            )
            if device_id is None:
                raise DashboardNotFound("Device not found.")
            start = now - HISTORY_RANGES[range_name]
            rows = session.scalars(
                select(HeartbeatSample)
                .where(
                    HeartbeatSample.device_id == device_id,
                    HeartbeatSample.received_at >= start,
                    HeartbeatSample.received_at <= now,
                )
                .order_by(HeartbeatSample.received_at.desc(), HeartbeatSample.id.desc())
                .limit(HISTORY_RAW_CAP + 1)
            ).all()
            truncated = len(rows) > HISTORY_RAW_CAP
            retained = list(reversed(rows[:HISTORY_RAW_CAP]))
            return {
                "range": range_name,
                "from": _timestamp(start),
                "to": _timestamp(now),
                "truncated": truncated,
                "raw_sample_count": len(retained),
                **downsample_history(retained),
            }

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
