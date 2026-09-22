"""Local identity administration; all device mutations share the ingestion row lock."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import Database, database_utc
from app.devices.credentials import (
    GeneratedCredential,
    InvalidCredential,
    generate_credential,
    parse_credential,
    verify_token,
)
from app.models import AuditEvent, Device, DeviceCredential, Project


class IdentityError(ValueError):
    """A safe operator-facing error; messages must not include external values."""


class NotFound(IdentityError):
    pass


class Conflict(IdentityError):
    pass


class AuthenticationFailed(IdentityError):
    def __init__(self) -> None:
        super().__init__("Device authentication failed.")


def _label(value: str, limit: int = 128) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise IdentityError("Label is empty or too long.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise IdentityError("Label contains control characters.")
    return value.strip()


def _uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise IdentityError("A valid UUID is required.") from None
    return str(parsed)


@dataclass(frozen=True)
class GPUPolicy:
    monitoring_enabled: bool = True
    min_count: int = 1
    uuids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.monitoring_enabled) is not bool or type(self.min_count) is not int:
            raise IdentityError("GPU policy requires a boolean and integer count.")
        if not 0 <= self.min_count <= 64 or len(self.uuids) > 64:
            raise IdentityError("GPU policy exceeds supported inventory bounds.")
        if len(set(self.uuids)) != len(self.uuids) or any(
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", value)
            for value in self.uuids
        ):
            raise IdentityError("GPU identifiers must be unique bounded identifiers.")
        if not self.monitoring_enabled and (self.min_count or self.uuids):
            raise IdentityError("Disabled GPU monitoring requires an empty expected inventory.")


@dataclass(frozen=True)
class Enrollment:
    device: Device
    credential: GeneratedCredential


DEFAULT_GPU_POLICY = GPUPolicy()


def lock_device(session: Session, device_uuid: str) -> Device:
    device = session.scalar(
        select(Device)
        .where(Device.device_uuid == _uuid(device_uuid))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if device is None:
        raise NotFound("Device not found.")
    return device


class IdentityService:
    def __init__(self, database: Database, actor: str) -> None:
        self.database = database
        if not re.fullmatch(r"[A-Za-z0-9_@.\-]{1,128}", actor) or actor.startswith("sb1."):
            raise IdentityError("A bounded operator identifier is required.")
        self.actor = actor

    def _audit(
        self,
        session: Session,
        action: str,
        now: datetime,
        *,
        device: Device | None = None,
        project: Project | None = None,
        details: dict[str, str | int | bool] | None = None,
    ) -> None:
        session.add(
            AuditEvent(
                actor=self.actor,
                action=action,
                occurred_at=now,
                device_id=device.id if device else None,
                project_id=project.id if project else device.project_id if device else None,
                details=details or {},
            )
        )

    @staticmethod
    def _project(session: Session, public_id: str) -> Project:
        project = session.scalar(
            select(Project)
            .where(Project.public_id == _uuid(public_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None:
            raise NotFound("Project not found.")
        return project

    @staticmethod
    def _expiry(value: datetime | None, now: datetime) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise IdentityError("Credential expiration requires an explicit timezone.")
        normalized = value.astimezone(UTC).replace(tzinfo=None)
        if normalized <= now:
            raise IdentityError("Credential expiration must be in the future.")
        return normalized

    def _credential(
        self, session: Session, device: Device, now: datetime, expires_at: datetime | None
    ) -> GeneratedCredential:
        generated = generate_credential()
        session.add(
            DeviceCredential(
                credential_id=generated.credential_id,
                device_id=device.id,
                token_digest=generated.digest,
                created_at=now,
                expires_at=expires_at,
            )
        )
        self._audit(
            session,
            "credential.created",
            now,
            device=device,
            details={"credential_id": generated.credential_id},
        )
        return generated

    def create_project(self, name: str, description: str | None = None) -> Project:
        name = _label(name)
        description = _label(description, 512) if description else None
        with self.database.transaction() as session:
            now = database_utc(session)
            project = Project(
                public_id=str(uuid4()),
                name=name,
                description=description,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(project)
            session.flush()
            self._audit(session, "project.created", now, project=project)
        return project

    def update_project(
        self,
        project_uuid: str,
        *,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> Project:
        with self.database.transaction() as session:
            project = self._project(session, project_uuid)
            now = database_utc(session)
            if name is not None:
                project.name = _label(name)
            if description is not None:
                project.description = _label(description, 512) if description else None
            if is_active is not None:
                project.is_active = is_active
            project.updated_at = now
            self._audit(session, "project.updated", now, project=project)
        return project

    def enroll(
        self,
        project_uuid: str,
        name: str,
        *,
        policy: GPUPolicy = DEFAULT_GPU_POLICY,
        expires_at: datetime | None = None,
    ) -> Enrollment:
        name = _label(name)
        with self.database.transaction() as session:
            project = self._project(session, project_uuid)
            if not project.is_active:
                raise Conflict("Project is inactive.")
            now = database_utc(session)
            expiry = self._expiry(expires_at, now)
            device = Device(
                device_uuid=str(uuid4()),
                project_id=project.id,
                name=name,
                monitoring_enabled=True,
                monitoring_started_at=now,
                gpu_monitoring_enabled=policy.monitoring_enabled,
                expected_gpu_min_count=policy.min_count,
                expected_gpu_uuids=list(policy.uuids),
                created_at=now,
                updated_at=now,
            )
            session.add(device)
            session.flush()
            self._audit(session, "device.enrolled", now, device=device)
            credential = self._credential(session, device, now, expiry)
        return Enrollment(device, credential)

    def get_device(self, device_uuid: str) -> Device:
        with self.database.transaction() as session:
            device = session.scalar(select(Device).where(Device.device_uuid == _uuid(device_uuid)))
            if device is None:
                raise NotFound("Device not found.")
        return device

    def rename(self, device_uuid: str, name: str) -> Device:
        name = _label(name)
        with self.database.transaction() as session:
            device = lock_device(session, device_uuid)
            device.name = name
            device.updated_at = database_utc(session)
            self._audit(session, "device.renamed", device.updated_at, device=device)
        return device

    def move(self, device_uuid: str, project_uuid: str) -> Device:
        with self.database.transaction() as session:
            device = lock_device(session, device_uuid)
            project = self._project(session, project_uuid)
            if not project.is_active:
                raise Conflict("Project is inactive.")
            previous = device.project_id
            device.project_id = project.id
            device.updated_at = database_utc(session)
            self._audit(
                session,
                "device.moved",
                device.updated_at,
                device=device,
                details={"previous_project_id": previous},
            )
        return device

    def set_enabled(self, device_uuid: str, enabled: bool) -> Device:
        with self.database.transaction() as session:
            device = lock_device(session, device_uuid)
            if device.monitoring_enabled != enabled:
                now = database_utc(session)
                device.monitoring_enabled = enabled
                device.updated_at = now
                if enabled:
                    device.monitoring_started_at = now
                self._audit(
                    session, "device.enabled" if enabled else "device.disabled", now, device=device
                )
        return device

    def set_gpu_policy(self, device_uuid: str, policy: GPUPolicy) -> Device:
        with self.database.transaction() as session:
            device = lock_device(session, device_uuid)
            device.gpu_monitoring_enabled = policy.monitoring_enabled
            device.expected_gpu_min_count = policy.min_count
            device.expected_gpu_uuids = list(policy.uuids)
            device.updated_at = database_utc(session)
            self._audit(session, "device.gpu_policy_changed", device.updated_at, device=device)
        return device

    def rotate(
        self, device_uuid: str, *, overlap_hours: int = 24, expires_at: datetime | None = None
    ) -> GeneratedCredential:
        if type(overlap_hours) is not int or not 1 <= overlap_hours <= 24:
            raise IdentityError("Rotation overlap must be between 1 and 24 hours.")
        with self.database.transaction() as session:
            device = lock_device(session, device_uuid)
            now = database_utc(session)
            expiry = self._expiry(expires_at, now)
            active = session.scalars(
                select(DeviceCredential).where(
                    DeviceCredential.device_id == device.id,
                    DeviceCredential.revoked_at.is_(None),
                    or_(DeviceCredential.expires_at.is_(None), DeviceCredential.expires_at > now),
                )
            ).all()
            if len(active) >= 2:
                raise Conflict("Two credentials are already active; finish the existing rotation.")
            overlap_end = now + timedelta(hours=overlap_hours)
            for credential in active:
                credential.expires_at = min(credential.expires_at or overlap_end, overlap_end)
            generated = self._credential(session, device, now, expiry)
            self._audit(
                session,
                "credential.rotated",
                now,
                device=device,
                details={"credential_id": generated.credential_id, "overlap_hours": overlap_hours},
            )
        return generated

    def revoke(self, device_uuid: str, credential_id: str) -> None:
        with self.database.transaction() as session:
            device = lock_device(session, device_uuid)
            credential = session.scalar(
                select(DeviceCredential).where(
                    DeviceCredential.credential_id == _uuid(credential_id),
                    DeviceCredential.device_id == device.id,
                )
            )
            if credential is None:
                raise NotFound("Credential not found for device.")
            if credential.revoked_at is None:
                now = database_utc(session)
                credential.revoked_at = now
                self._audit(
                    session,
                    "credential.revoked",
                    now,
                    device=device,
                    details={"credential_id": credential.credential_id},
                )

    def authenticate(self, session: Session, device_uuid: str, token: str) -> Device:
        """Caller owns transaction. Device lock remains held until commit/rollback."""
        try:
            parsed = parse_credential(token)
            device = lock_device(session, device_uuid)
        except (InvalidCredential, IdentityError):
            raise AuthenticationFailed() from None
        credential = session.scalar(
            select(DeviceCredential)
            .where(
                DeviceCredential.credential_id == parsed.credential_id,
                DeviceCredential.device_id == device.id,
            )
            .execution_options(populate_existing=True)
        )
        now = database_utc(session)
        if (
            credential is None
            or not device.monitoring_enabled
            or credential.revoked_at is not None
            or (credential.expires_at is not None and credential.expires_at <= now)
            or not verify_token(token, credential.token_digest)
        ):
            raise AuthenticationFailed()
        return device

    def authenticate_token(self, session: Session, token: str) -> Device:
        """Authenticate the credential binding before the caller compares external identity."""
        try:
            parsed = parse_credential(token)
        except InvalidCredential:
            raise AuthenticationFailed() from None
        credential = session.scalar(
            select(DeviceCredential).where(DeviceCredential.credential_id == parsed.credential_id)
        )
        if credential is None:
            raise AuthenticationFailed()
        device = session.scalar(
            select(Device)
            .where(Device.id == credential.device_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if device is None:
            raise AuthenticationFailed()
        credential = session.scalar(
            select(DeviceCredential)
            .where(
                DeviceCredential.credential_id == parsed.credential_id,
                DeviceCredential.device_id == device.id,
            )
            .execution_options(populate_existing=True)
        )
        now = database_utc(session)
        if (
            credential is None
            or not device.monitoring_enabled
            or credential.revoked_at is not None
            or (credential.expires_at is not None and credential.expires_at <= now)
            or not verify_token(token, credential.token_digest)
        ):
            raise AuthenticationFailed()
        return device
