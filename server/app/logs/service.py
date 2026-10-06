"""Device-bound, bounded Log Watch storage."""

from collections.abc import Callable
from datetime import UTC, timedelta
from uuid import UUID

from sqlalchemy import delete, select

from app.dashboard.read import DashboardNotFound
from app.db import Database, database_utc
from app.devices.service import IdentityService
from app.heartbeats.service import wire_time
from app.models import Device, DeviceLogEntry, DeviceLogSource
from app.schemas.logs import LOG_SOURCES, LogUpload

MAX_STORED_PER_SOURCE = 500


class LogTimestampInvalid(ValueError):
    pass


class LogRateLimited(ValueError):
    pass


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
                            DeviceLogEntry.source == upload.source,
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
                "received_at": wire_time(now),
            }

    def recent(
        self, device_uuid: str, *, source: str | None = None, limit: int = 60
    ) -> dict[str, object]:
        if source is not None and source not in LOG_SOURCES:
            raise ValueError("Invalid log source.")
        if not 1 <= limit <= 100:
            raise ValueError("Invalid log limit.")
        try:
            canonical = str(UUID(device_uuid))
        except (TypeError, ValueError):
            raise DashboardNotFound("Device not found.") from None
        if canonical != device_uuid:
            raise DashboardNotFound("Device not found.")
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
            entries = session.scalars(query.order_by(DeviceLogEntry.id.desc()).limit(limit)).all()
            return {
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
