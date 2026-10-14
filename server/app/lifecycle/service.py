"""Durable one-device lifecycle intent and approved-release binding."""

import hashlib
import re
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Database, database_utc
from app.devices.service import IdentityService, NotFound, lock_device
from app.heartbeats.service import wire_time
from app.models import AuditEvent, Device, DeviceAgentLifecycle, DeviceLatest
from app.releases.service import AgentReleaseService, ReleaseUnavailable

ACTIVE = frozenset(
    {"REQUESTED", "DOWNLOADING", "VERIFYING", "INSTALLING", "RESTARTING", "VERIFYING_HEALTH"}
)
TERMINAL = frozenset({"SUCCEEDED", "FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"})
FAILURES = frozenset(
    {
        "verification_failed",
        "installation_failed",
        "service_start_failed",
        "health_check_failed",
        "rollback_failed",
    }
)
DETAIL_CATEGORY = {
    "archive_digest_mismatch": "verification_failed",
    "bundle_verification_failed": "verification_failed",
    "previous_release_mismatch": "verification_failed",
    "installer_failed": "installation_failed",
    "interrupted_switch": "installation_failed",
    "rollback_target_unhealthy": "health_check_failed",
    "previous_service_unhealthy": "rollback_failed",
}
FAILURE_DETAILS = frozenset(DETAIL_CATEGORY)
PROGRESS = ("REQUESTED", "DOWNLOADING", "VERIFYING", "INSTALLING", "RESTARTING", "VERIFYING_HEALTH")
FIRST_CAPABLE_VERSION = (1, 0, 4)


class LifecycleConflict(ValueError):
    pass


def _version(value: str | None) -> tuple[int, int, int] | None:
    if value is None or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value) is None:
        return None
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        raise ReleaseUnavailable("Agent release is unavailable.") from None
    return digest.hexdigest()


def _view(operation: DeviceAgentLifecycle | None) -> dict[str, object] | None:
    if operation is None:
        return None
    return {
        "operation_id": operation.operation_uuid,
        "action": operation.action,
        "state": operation.state,
        "target_version": operation.target_version,
        "target_wheel_sha256": operation.target_wheel_sha256,
        "archive_sha256": operation.archive_sha256,
        "previous_version": operation.previous_version,
        "failure_category": operation.failure_category,
        "failure_detail": operation.failure_detail,
        "rollback_available": operation.rollback_available,
        "requested_at": wire_time(operation.requested_at),
        "updated_at": wire_time(operation.updated_at),
        "completed_at": wire_time(operation.completed_at) if operation.completed_at else None,
    }


class AgentLifecycleService:
    def __init__(self, database: Database, releases: AgentReleaseService) -> None:
        self.database = database
        self.releases = releases

    def overview(self, device_uuid: str) -> dict[str, object]:
        with self.database.transaction() as session:
            device = session.scalar(
                select(Device).where(Device.device_uuid == str(UUID(device_uuid)))
            )
            if device is None or device.device_uuid != device_uuid:
                raise NotFound("Device not found.")
            latest = session.get(DeviceLatest, device.id)
            operation = session.get(DeviceAgentLifecycle, device.id)
            installed = latest.agent_version if latest is not None else None
        try:
            approved = self.releases.current().version
        except ReleaseUnavailable:
            approved = None
        current = _version(installed)
        target = _version(approved)
        if operation is not None and operation.state in ACTIVE:
            status = "IN_PROGRESS"
        elif current is None:
            status = "UNKNOWN"
        elif current < FIRST_CAPABLE_VERSION:
            status = "BOOTSTRAP_REQUIRED"
        elif target is None:
            status = "RELEASE_UNAVAILABLE"
        elif current == target:
            status = "CURRENT"
        elif current < target:
            status = "UPGRADE_AVAILABLE"
        else:
            status = "NEWER_THAN_APPROVED"
        upgrade_allowed = status == "UPGRADE_AVAILABLE" and not (
            operation is not None
            and operation.state == "SUCCEEDED"
            and operation.target_version == approved
        )
        rollback_allowed = (
            operation is not None
            and operation.state == "SUCCEEDED"
            and operation.rollback_available
            and operation.previous_version is not None
            and operation.previous_wheel_sha256 is not None
            and installed == operation.target_version
        )
        return {
            "installed_version": installed,
            "latest_approved_version": approved,
            "compatibility": status,
            "operation": _view(operation),
            "actions": {"upgrade": upgrade_allowed, "rollback": rollback_allowed},
        }

    def request_upgrade(self, device_uuid: str, actor: str) -> dict[str, object]:
        metadata = self.releases.current()
        archive_digest = _digest_file(self.releases.archive())
        target = _version(metadata.version)
        if target is None:
            raise ReleaseUnavailable("Agent release is unavailable.")
        with self.database.transaction() as session:
            device = lock_device(session, device_uuid)
            latest = session.get(DeviceLatest, device.id)
            installed = latest.agent_version if latest is not None else None
            current = _version(installed)
            prior = session.get(DeviceAgentLifecycle, device.id)
            if prior is not None and prior.state in ACTIVE:
                if prior.action == "UPGRADE" and prior.target_wheel_sha256 == metadata.wheel_sha256:
                    return {"operation": _view(prior)}
                raise LifecycleConflict("An agent lifecycle operation is active.")
            if (
                prior is not None
                and prior.state == "SUCCEEDED"
                and prior.target_wheel_sha256 == metadata.wheel_sha256
            ):
                return {"operation": _view(prior)}
            if current is None or current < FIRST_CAPABLE_VERSION or target <= current:
                raise LifecycleConflict("Agent upgrade is not available.")
            now = database_utc(session)
            operation = DeviceAgentLifecycle(
                device_id=device.id,
                operation_uuid=str(uuid4()),
                action="UPGRADE",
                state="REQUESTED",
                target_version=metadata.version,
                target_wheel_sha256=metadata.wheel_sha256,
                archive_sha256=archive_digest,
                previous_version=installed,
                previous_wheel_sha256=None,
                rollback_available=False,
                requester=actor,
                failure_category=None,
                failure_detail=None,
                requested_at=now,
                updated_at=now,
                completed_at=None,
            )
            if prior is not None:
                session.delete(prior)
                session.flush()
            session.add(operation)
            self._audit(session, device, actor, "agent.upgrade.requested", now, operation)
            return {"operation": _view(operation)}

    def request_rollback(self, device_uuid: str, actor: str) -> dict[str, object]:
        with self.database.transaction() as session:
            device = lock_device(session, device_uuid)
            prior = session.get(DeviceAgentLifecycle, device.id)
            if prior is None or prior.state != "SUCCEEDED" or not prior.rollback_available:
                raise LifecycleConflict("No known-good previous release is available.")
            if prior.previous_version is None or prior.previous_wheel_sha256 is None:
                raise LifecycleConflict("No known-good previous release is available.")
            latest = session.get(DeviceLatest, device.id)
            if latest is None or latest.agent_version != prior.target_version:
                raise LifecycleConflict(
                    "Await a heartbeat from the installed release before rollback."
                )
            now = database_utc(session)
            operation = DeviceAgentLifecycle(
                device_id=device.id,
                operation_uuid=str(uuid4()),
                action="ROLLBACK",
                state="REQUESTED",
                target_version=prior.previous_version,
                target_wheel_sha256=prior.previous_wheel_sha256,
                archive_sha256=None,
                previous_version=prior.target_version,
                previous_wheel_sha256=prior.target_wheel_sha256,
                rollback_available=False,
                requester=actor,
                failure_category=None,
                failure_detail=None,
                requested_at=now,
                updated_at=now,
                completed_at=None,
            )
            session.delete(prior)
            session.flush()
            session.add(operation)
            self._audit(session, device, actor, "agent.rollback.requested", now, operation)
            return {"operation": _view(operation)}

    def device_operation(self, token: str) -> dict[str, object]:
        with self.database.transaction() as session:
            device = IdentityService(self.database, actor="agent_lifecycle").authenticate_token(
                session, token
            )
            operation = session.get(DeviceAgentLifecycle, device.id)
            return {
                "operation": _view(operation) if operation and operation.state in ACTIVE else None
            }

    def device_archive(self, token: str, operation_id: str) -> Path:
        with self.database.transaction() as session:
            device = IdentityService(self.database, actor="agent_lifecycle").authenticate_token(
                session, token
            )
            operation = session.get(DeviceAgentLifecycle, device.id)
            if (
                operation is None
                or operation.operation_uuid != operation_id
                or operation.action != "UPGRADE"
                or operation.state not in ACTIVE
            ):
                raise NotFound("Agent release is unavailable.")
            version = operation.target_version
            wheel_sha = operation.target_wheel_sha256
            archive_sha = operation.archive_sha256
        metadata = self.releases.current()
        archive = self.releases.archive()
        if (
            metadata.version != version
            or metadata.wheel_sha256 != wheel_sha
            or _digest_file(archive) != archive_sha
        ):
            raise ReleaseUnavailable("Agent release is unavailable.")
        return archive

    def device_report(
        self,
        token: str,
        operation_id: str,
        state: str,
        *,
        failure_category: str | None = None,
        failure_detail: str | None = None,
        previous_wheel_sha256: str | None = None,
        rollback_available: bool = False,
    ) -> dict[str, object]:
        if state not in ACTIVE | TERMINAL or state == "REQUESTED":
            raise ValueError("Invalid lifecycle state.")
        if failure_category not in FAILURES | {None}:
            raise ValueError("Invalid lifecycle failure category.")
        if failure_detail not in FAILURE_DETAILS | {None}:
            raise ValueError("Invalid lifecycle failure detail.")
        if failure_detail is not None and failure_category is None:
            raise ValueError("Lifecycle failure detail requires a category.")
        if failure_detail is not None and DETAIL_CATEGORY[failure_detail] != failure_category:
            raise ValueError("Lifecycle failure detail does not match its category.")
        if state in {"FAILED", "ROLLBACK_FAILED"} and failure_category is None:
            raise ValueError("Lifecycle failure requires a category.")
        if (
            state not in {"FAILED", "ROLLBACK_FAILED", "ROLLED_BACK"}
            and failure_category is not None
        ):
            raise ValueError("Lifecycle progress cannot include a failure category.")
        if (
            previous_wheel_sha256 is not None
            and re.fullmatch(r"[0-9a-f]{64}", previous_wheel_sha256) is None
        ):
            raise ValueError("Invalid previous release digest.")
        if previous_wheel_sha256 is not None and state != "SUCCEEDED":
            raise ValueError("Previous release digest requires upgrade success.")
        if rollback_available and (state != "SUCCEEDED" or previous_wheel_sha256 is None):
            raise ValueError("Rollback availability requires a verified previous release.")
        with self.database.transaction() as session:
            device = IdentityService(self.database, actor="agent_lifecycle").authenticate_token(
                session, token
            )
            device = lock_device(session, device.device_uuid)
            operation = session.get(DeviceAgentLifecycle, device.id)
            if operation is None or operation.operation_uuid != operation_id:
                raise NotFound("Agent lifecycle operation not found.")
            if operation.state == state:
                if state in TERMINAL and (
                    operation.failure_category != failure_category
                    or operation.failure_detail != failure_detail
                    or operation.rollback_available != rollback_available
                    or (
                        state == "SUCCEEDED"
                        and operation.previous_wheel_sha256 != previous_wheel_sha256
                    )
                ):
                    raise LifecycleConflict(
                        "Agent lifecycle result differs from the recorded result."
                    )
                return {"operation": _view(operation)}
            if operation.state in TERMINAL:
                raise LifecycleConflict("Agent lifecycle operation is complete.")
            if state in ACTIVE and PROGRESS.index(state) <= PROGRESS.index(operation.state):
                raise LifecycleConflict("Agent lifecycle status is out of order.")
            if (
                state == "ROLLED_BACK"
                and operation.action != "ROLLBACK"
                and failure_category is None
            ):
                raise ValueError("Rollback requires a failure category.")
            if state == "SUCCEEDED" and operation.action != "UPGRADE":
                raise ValueError("Rollback operation cannot report upgrade success.")
            if (
                state == "ROLLED_BACK"
                and operation.action == "ROLLBACK"
                and failure_category is not None
            ):
                raise ValueError("Operator rollback has no upgrade failure category.")
            now = database_utc(session)
            operation.state = state
            operation.updated_at = now
            operation.failure_category = failure_category if state in TERMINAL else None
            operation.failure_detail = failure_detail if state in TERMINAL else None
            if state in TERMINAL:
                operation.completed_at = now
            if state == "SUCCEEDED" and previous_wheel_sha256 is not None:
                operation.previous_wheel_sha256 = previous_wheel_sha256
                operation.rollback_available = rollback_available
            if state in TERMINAL:
                self._audit(
                    session, device, "agent_lifecycle", f"agent.{state.lower()}", now, operation
                )
            return {"operation": _view(operation)}

    @staticmethod
    def _audit(
        session: Session,
        device: Device,
        actor: str,
        action: str,
        now: datetime,
        operation: DeviceAgentLifecycle,
    ) -> None:
        session.add(
            AuditEvent(
                actor=actor,
                action=action,
                project_id=device.project_id,
                device_id=device.id,
                occurred_at=now,
                details={
                    "operation_id": operation.operation_uuid,
                    "action": operation.action,
                    "target_version": operation.target_version,
                    "previous_version": operation.previous_version,
                    "state": operation.state,
                    "failure_category": operation.failure_category,
                    "failure_detail": operation.failure_detail,
                },
            )
        )
