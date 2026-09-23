"""Transactional heartbeat ingestion; external side effects are deliberately absent."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.db import Database, database_utc
from app.devices.service import IdentityService
from app.gpu.service import GPUIncidentService
from app.health.service import AvailabilityService
from app.models import DeviceLatest, HeartbeatReceipt, HeartbeatSample
from app.schemas.heartbeat import Heartbeat, normalized_payload, payload_digest


class HeartbeatConflict(ValueError):
    pass


class HeartbeatIdentityMismatch(ValueError):
    pass


class HeartbeatRateLimited(ValueError):
    pass


@dataclass(frozen=True)
class AcceptedHeartbeat:
    payload: dict[str, str | int]


def wire_time(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class HeartbeatService:
    def __init__(
        self,
        database: Database,
        *,
        allowed: Callable[[int], bool],
        email_recipients: tuple[str, ...] = (),
        sms_recipients: tuple[str, ...] = (),
    ) -> None:
        self.database = database
        self.allowed = allowed
        self.availability = AvailabilityService(
            database, email_recipients=email_recipients, sms_recipients=sms_recipients
        )
        self.gpu = GPUIncidentService(
            email_recipients=email_recipients, sms_recipients=sms_recipients
        )

    def accept(self, heartbeat: Heartbeat, token: str) -> AcceptedHeartbeat:
        digest = payload_digest(heartbeat)
        payload = normalized_payload(heartbeat)
        with self.database.transaction() as session:
            device = IdentityService(self.database, actor="heartbeat").authenticate_token(
                session, token
            )
            if device.device_uuid != heartbeat.device_id:
                raise HeartbeatIdentityMismatch()
            if not self.allowed(device.id):
                raise HeartbeatRateLimited()
            receipt = session.get(
                HeartbeatReceipt, {"device_id": device.id, "heartbeat_id": heartbeat.heartbeat_id}
            )
            if receipt is not None:
                if receipt.payload_hash != digest:
                    raise HeartbeatConflict()
                return AcceptedHeartbeat(receipt.response_payload)
            received_at = database_utc(session)
            self.availability.accept_heartbeat(session, device, received_at)
            self.gpu.accept(session, device, payload, received_at)
            acknowledgement: dict[str, str | int] = {
                "schema_version": 1,
                "heartbeat_id": heartbeat.heartbeat_id,
                "device_id": heartbeat.device_id,
                "accepted_at": wire_time(received_at),
            }
            session.add(
                HeartbeatReceipt(
                    device_id=device.id,
                    heartbeat_id=heartbeat.heartbeat_id,
                    payload_hash=digest,
                    received_at=received_at,
                    expires_at=received_at + timedelta(hours=24),
                    response_payload=acknowledgement,
                )
            )
            session.add(
                HeartbeatSample(
                    device_id=device.id,
                    heartbeat_id=heartbeat.heartbeat_id,
                    received_at=received_at,
                    collected_at=heartbeat.collected_at.replace(tzinfo=None),
                    schema_version=heartbeat.schema_version,
                    agent_version=heartbeat.agent_version,
                    payload=payload,
                )
            )
            latest = session.get(DeviceLatest, device.id)
            values = {
                "heartbeat_id": heartbeat.heartbeat_id,
                "received_at": received_at,
                "collected_at": heartbeat.collected_at.replace(tzinfo=None),
                "schema_version": heartbeat.schema_version,
                "agent_version": heartbeat.agent_version,
                "hostname": heartbeat.hostname,
                "primary_ip": heartbeat.ip_addresses[0] if heartbeat.ip_addresses else None,
                "cpu_percent": heartbeat.cpu.utilization_percent,
                "memory_percent": heartbeat.memory.utilization_percent,
                "disk_summary": {"count": len(heartbeat.disks)},
                "gpu_summary": heartbeat.gpu_health.model_dump(mode="json"),
                "payload": payload,
            }
            if latest is None:
                session.add(DeviceLatest(device_id=device.id, **values))
            else:
                for key, value in values.items():
                    setattr(latest, key, value)
        return AcceptedHeartbeat(acknowledgement)
