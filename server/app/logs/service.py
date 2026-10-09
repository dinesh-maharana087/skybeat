"""Device-bound, bounded Log Watch storage."""

import base64
import binascii
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, tuple_

from app.dashboard.read import DashboardNotFound
from app.db import Database, database_utc
from app.devices.service import IdentityService
from app.heartbeats.service import wire_time
from app.models import Device, DeviceLogEntry, DeviceLogSource
from app.schemas.logs import LOG_SOURCES, LogUpload

MAX_STORED_PER_SOURCE = 500
RETENTION_BATCH_SIZE = 500
_QUERY_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z"
)


def _parse_query_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not _QUERY_TIME.fullmatch(value):
        raise ValueError("Log time filter is invalid.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Log time filter is invalid.") from None
    return parsed.astimezone(UTC).replace(tzinfo=None)


def parse_log_window(
    from_time: str | None, until: str | None
) -> tuple[datetime | None, datetime | None]:
    start, end = _parse_query_time(from_time), _parse_query_time(until)
    if start is not None and end is not None and start > end:
        raise ValueError("Log time window is reversed.")
    return start, end


def _cursor_time(value: datetime | None) -> str | None:
    return value.isoformat(timespec="microseconds") if value is not None else None


def encode_log_cursor(
    last_id: int,
    device_uuid: str,
    source: str | None,
    from_time: datetime | None,
    until: datetime | None,
    direction: str,
) -> str:
    raw = json.dumps(
        {
            "v": 1,
            "id": last_id,
            "device": device_uuid,
            "source": source,
            "from": _cursor_time(from_time),
            "until": _cursor_time(until),
            "direction": direction,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_log_cursor(
    value: str,
    device_uuid: str,
    source: str | None,
    from_time: datetime | None,
    until: datetime | None,
    direction: str,
) -> int:
    if not value or len(value) > 512:
        raise ValueError("Log cursor is invalid.")
    try:
        raw = value.encode("ascii")
        payload = json.loads(
            base64.b64decode(raw + b"=" * (-len(raw) % 4), altchars=b"-_", validate=True)
        )
    except (UnicodeEncodeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        raise ValueError("Log cursor is invalid.") from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"v", "id", "device", "source", "from", "until", "direction"}
        or payload["v"] != 1
        or not isinstance(payload["id"], int)
        or isinstance(payload["id"], bool)
        or not 1 <= payload["id"] <= 2**64 - 1
        or payload["device"] != device_uuid
        or payload["source"] != source
        or payload["from"] != _cursor_time(from_time)
        or payload["until"] != _cursor_time(until)
        or payload["direction"] != direction
    ):
        raise ValueError("Log cursor is invalid.")
    return payload["id"]


class LogTimestampInvalid(ValueError):
    pass


class LogRateLimited(ValueError):
    pass


class LogRetentionService:
    """Delete at most one indexed batch from each diagnostics table per call."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def prune_expired(self, *, retention_days: int) -> tuple[int, int]:
        if not 1 <= retention_days <= 365:
            raise ValueError("Diagnostics retention is invalid.")
        with self.database.transaction() as session:
            cutoff = database_utc(session) - timedelta(days=retention_days)
            entry_ids = session.scalars(
                select(DeviceLogEntry.id)
                .where(DeviceLogEntry.received_at < cutoff)
                .order_by(DeviceLogEntry.received_at, DeviceLogEntry.id)
                .limit(RETENTION_BATCH_SIZE)
            ).all()
            if entry_ids:
                session.execute(delete(DeviceLogEntry).where(DeviceLogEntry.id.in_(entry_ids)))
            source_keys = session.execute(
                select(DeviceLogSource.device_id, DeviceLogSource.source)
                .where(DeviceLogSource.checked_at < cutoff)
                .order_by(
                    DeviceLogSource.checked_at,
                    DeviceLogSource.device_id,
                    DeviceLogSource.source,
                )
                .limit(RETENTION_BATCH_SIZE)
            ).all()
            if source_keys:
                session.execute(
                    delete(DeviceLogSource).where(
                        tuple_(DeviceLogSource.device_id, DeviceLogSource.source).in_(source_keys),
                        DeviceLogSource.checked_at < cutoff,
                    )
                )
            return len(entry_ids), len(source_keys)


class LogWatchService:
    def __init__(self, database: Database, *, allowed: Callable[[int], bool] | None = None) -> None:
        self.database = database
        self.allowed = allowed or (lambda _: True)

    def accept(self, upload: LogUpload, token: str) -> dict[str, object]:
        with self.database.transaction() as session:
            device = IdentityService(self.database, actor="log_watch").authenticate_token(
                session, token
            )
            if not self.allowed(device.id):
                raise LogRateLimited()
            now = database_utc(session)
            hashes = [bytes.fromhex(entry.entry_id) for entry in upload.entries]
            existing = (
                set(
                    session.scalars(
                        select(DeviceLogEntry.entry_hash).where(
                            DeviceLogEntry.device_id == device.id,
                            DeviceLogEntry.entry_hash.in_(hashes),
                        )
                    )
                )
                if hashes
                else set()
            )
            seen = set(existing)
            for entry in upload.entries:
                digest = bytes.fromhex(entry.entry_id)
                if digest in seen:
                    continue
                seen.add(digest)
                if entry.occurred_at is not None:
                    occurred = entry.occurred_at.astimezone(UTC).replace(tzinfo=None)
                    if occurred < now - timedelta(days=1) or occurred > now + timedelta(minutes=5):
                        raise LogTimestampInvalid()
                else:
                    occurred = None
                session.add(
                    DeviceLogEntry(
                        device_id=device.id,
                        source=upload.source,
                        entry_hash=digest,
                        occurred_at=occurred,
                        received_at=now,
                        severity=entry.severity,
                        message=entry.message,
                    )
                )
            session.flush()
            source_state = session.get(DeviceLogSource, (device.id, upload.source))
            if source_state is None:
                session.add(
                    DeviceLogSource(
                        device_id=device.id,
                        source=upload.source,
                        status=upload.status,
                        checked_at=now,
                    )
                )
            else:
                source_state.status = upload.status
                source_state.checked_at = now
            cutoff_id = session.scalar(
                select(DeviceLogEntry.id)
                .where(
                    DeviceLogEntry.device_id == device.id, DeviceLogEntry.source == upload.source
                )
                .order_by(DeviceLogEntry.id.desc())
                .offset(MAX_STORED_PER_SOURCE - 1)
                .limit(1)
            )
            if cutoff_id is not None:
                session.execute(
                    delete(DeviceLogEntry).where(
                        DeviceLogEntry.device_id == device.id,
                        DeviceLogEntry.source == upload.source,
                        DeviceLogEntry.id < cutoff_id,
                    )
                )
            return {
                "source": upload.source,
                "accepted": len(seen) - len(existing),
                "duplicates": len(upload.entries) - (len(seen) - len(existing)),
                "received_at": wire_time(now),
            }

    def recent(
        self,
        device_uuid: str,
        *,
        source: str | None = None,
        limit: int = 60,
        from_time: str | None = None,
        until: str | None = None,
        cursor: str | None = None,
        direction: str = "newest",
    ) -> dict[str, object]:
        if source is not None and source not in LOG_SOURCES:
            raise ValueError("Invalid log source.")
        if not 1 <= limit <= 100:
            raise ValueError("Invalid log limit.")
        if direction not in {"newest", "oldest"}:
            raise ValueError("Invalid log direction.")
        start, end = parse_log_window(from_time, until)
        try:
            canonical = str(UUID(device_uuid))
        except (TypeError, ValueError):
            raise DashboardNotFound("Device not found.") from None
        if canonical != device_uuid:
            raise DashboardNotFound("Device not found.")
        last_id = (
            decode_log_cursor(cursor, canonical, source, start, end, direction)
            if cursor is not None
            else None
        )
        with self.database.transaction() as session:
            device_id = session.scalar(select(Device.id).where(Device.device_uuid == canonical))
            if device_id is None:
                raise DashboardNotFound("Device not found.")
            states = {
                item.source: item
                for item in session.scalars(
                    select(DeviceLogSource).where(DeviceLogSource.device_id == device_id)
                )
            }
            query = select(DeviceLogEntry).where(DeviceLogEntry.device_id == device_id)
            if source is not None:
                query = query.where(DeviceLogEntry.source == source)
            if start is not None:
                query = query.where(DeviceLogEntry.received_at >= start)
            if end is not None:
                query = query.where(DeviceLogEntry.received_at <= end)
            if last_id is not None:
                query = query.where(
                    DeviceLogEntry.id < last_id
                    if direction == "newest"
                    else DeviceLogEntry.id > last_id
                )
            order = DeviceLogEntry.id.desc() if direction == "newest" else DeviceLogEntry.id.asc()
            rows = session.scalars(query.order_by(order).limit(limit + 1)).all()
            entries = rows[:limit]
            next_cursor = (
                encode_log_cursor(entries[-1].id, canonical, source, start, end, direction)
                if len(rows) > limit
                else None
            )
            return {
                "next_cursor": next_cursor,
                "sources": [
                    {
                        "source": name,
                        "status": states[name].status if name in states else "no_report",
                        "checked_at": wire_time(states[name].checked_at)
                        if name in states
                        else None,
                    }
                    for name in LOG_SOURCES
                ],
                "items": [
                    {
                        "source": item.source,
                        "occurred_at": wire_time(item.occurred_at) if item.occurred_at else None,
                        "received_at": wire_time(item.received_at),
                        "severity": item.severity,
                        "message": item.message,
                    }
                    for item in entries
                ],
            }
