"""Secret-safe opaque tokens used by agent enrollment and verification receipts."""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Database, database_utc
from app.devices.credentials import GeneratedCredential
from app.devices.service import Conflict, GPUPolicy, IdentityService, NotFound, lock_device
from app.models import AgentEnrollment, AuditEvent, Device, Project


class TokenRejected(ValueError):
    """An enrollment token is malformed or unsuitable for the requested purpose."""


class EnrollmentRejected(ValueError):
    """A token cannot be exchanged without revealing its lifecycle state."""

    def __init__(self) -> None:
        super().__init__("Enrollment authorization is invalid.")


class ReceiptRejected(ValueError):
    """A receipt cannot be verified without revealing its lifecycle state."""

    def __init__(self) -> None:
        super().__init__("Enrollment verification receipt is invalid.")


class EnrollmentMode(StrEnum):
    NEW = "NEW"
    REPLACE = "REPLACE"


class EnrollmentLifecycle(StrEnum):
    PENDING = "PENDING"
    ENROLLED = "ENROLLED"
    ONLINE = "ONLINE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


OPAQUE_COMPONENT_PATTERN = r"[A-Za-z0-9_-]{43}"


@dataclass(frozen=True)
class EnrollmentToken:
    """Opaque bearer token whose secret digest can be persisted without the raw value."""

    identifier: str
    prefix: str
    value: str = field(repr=False)
    secret_digest: bytes = field(repr=False)

    @classmethod
    def generate(cls, prefix: str, *, identifier: str | None = None) -> "EnrollmentToken":
        if prefix not in {"sbe1", "sbv1"}:
            raise ValueError("Enrollment token prefix is invalid.")
        if identifier is None:
            identifier = str(uuid4())
        else:
            try:
                identifier = str(UUID(identifier))
            except (TypeError, ValueError):
                raise ValueError("Enrollment token identifier is invalid.") from None
        value = f"{prefix}.{identifier}.{secrets.token_urlsafe(32)}"
        return cls(
            identifier=identifier,
            prefix=prefix,
            value=value,
            secret_digest=hashlib.sha256(value.encode("ascii")).digest(),
        )

    @classmethod
    def parse(cls, value: object, *, expected_prefix: str) -> "EnrollmentToken":
        if expected_prefix not in {"sbe1", "sbv1"} or not isinstance(value, str):
            raise TokenRejected("Enrollment token is invalid.")
        match = re.fullmatch(
            rf"{re.escape(expected_prefix)}\.([0-9a-f]{{8}}(?:-[0-9a-f]{{4}}){{3}}-[0-9a-f]{{12}})\.({OPAQUE_COMPONENT_PATTERN})",
            value,
        )
        if match is None:
            raise TokenRejected("Enrollment token is invalid.")
        try:
            identifier = str(UUID(match.group(1)))
        except ValueError as error:
            raise TokenRejected("Enrollment token is invalid.") from error
        return cls(
            identifier=identifier,
            prefix=expected_prefix,
            value=value,
            secret_digest=hashlib.sha256(value.encode("ascii")).digest(),
        )


@dataclass(frozen=True)
class IssuedEnrollmentIntent:
    enrollment: AgentEnrollment
    token: EnrollmentToken = field(repr=False)


@dataclass(frozen=True)
class EnrollmentExchange:
    device: Device
    credential: GeneratedCredential = field(repr=False)
    verification_token: EnrollmentToken = field(repr=False)


@dataclass(frozen=True)
class ReceiptVerification:
    accepted_heartbeat: bool


@dataclass(frozen=True)
class EnrollmentStatus:
    enrollment_id: str
    state: EnrollmentLifecycle
    expires_at: datetime
    device_id: str | None
    last_seen_at: datetime | None


ENROLLMENT_TTL = timedelta(minutes=10)
VERIFICATION_TTL = timedelta(minutes=10)


class AgentEnrollmentService:
    """Create and consume strictly one-time agent enrollment authorizations."""

    def __init__(
        self,
        database: Database,
        *,
        actor: str,
        enrollment_lifetime: timedelta = ENROLLMENT_TTL,
        verification_lifetime: timedelta = VERIFICATION_TTL,
        offline_after_seconds: int = 180,
    ) -> None:
        self.database = database
        self.identity = IdentityService(database, actor=actor)
        self.actor = self.identity.actor
        self._require_ttl(enrollment_lifetime)
        self._require_ttl(verification_lifetime)
        self.enrollment_lifetime = enrollment_lifetime
        self.verification_lifetime = verification_lifetime
        if not isinstance(offline_after_seconds, int) or offline_after_seconds < 1:
            raise ValueError("Offline threshold is invalid.")
        self.offline_after = timedelta(seconds=offline_after_seconds)

    @staticmethod
    def _require_ttl(value: timedelta) -> None:
        if not isinstance(value, timedelta) or not timedelta(seconds=1) <= value <= timedelta(
            minutes=30
        ):
            raise ValueError("Enrollment lifetime is invalid.")

    @staticmethod
    def _project(session: Session, project_uuid: str) -> Project:
        project = IdentityService._project(session, project_uuid)
        if not project.is_active:
            raise Conflict("Project is inactive.")
        return project

    def _audit(
        self,
        session: Session,
        action: str,
        now: datetime,
        enrollment: AgentEnrollment,
    ) -> None:
        session.add(
            AuditEvent(
                actor=self.actor,
                action=action,
                project_id=enrollment.project_id,
                device_id=enrollment.issued_device_id or enrollment.replacement_device_id,
                occurred_at=now,
                details={"enrollment_id": enrollment.public_id, "mode": enrollment.mode},
            )
        )

    def create_intent(
        self,
        *,
        mode: EnrollmentMode,
        project_uuid: str | None = None,
        replacement_device_uuid: str | None = None,
        device_name: str | None = None,
        policy: GPUPolicy | None = None,
        lifetime: timedelta | None = None,
    ) -> IssuedEnrollmentIntent:
        lifetime = self.enrollment_lifetime if lifetime is None else lifetime
        self._require_ttl(lifetime)
        token = EnrollmentToken.generate("sbe1")
        with self.database.transaction() as session:
            now = database_utc(session)
            project_id: int | None = None
            replacement_device_id: int | None = None
            if mode is EnrollmentMode.NEW:
                if project_uuid is None or device_name is None or policy is None:
                    raise ValueError("New enrollment intent is incomplete.")
                if replacement_device_uuid is not None:
                    raise ValueError("New enrollment cannot target an existing device.")
                project_id = self._project(session, project_uuid).id
            elif mode is EnrollmentMode.REPLACE:
                if (
                    replacement_device_uuid is None
                    or project_uuid is not None
                    or device_name is not None
                    or policy is not None
                ):
                    raise ValueError("Replacement enrollment intent is incomplete.")
                replacement_device_id = lock_device(session, replacement_device_uuid).id
            else:
                raise ValueError("Enrollment mode is invalid.")
            enrollment = AgentEnrollment(
                public_id=token.identifier,
                enrollment_digest=token.secret_digest,
                verification_digest=None,
                mode=mode.value,
                project_id=project_id,
                replacement_device_id=replacement_device_id,
                issued_device_id=None,
                device_name=device_name,
                gpu_monitoring_enabled=policy.monitoring_enabled if policy else None,
                expected_gpu_min_count=policy.min_count if policy else None,
                created_by=self.actor,
                created_at=now,
                expires_at=now + lifetime,
                used_at=None,
                verification_expires_at=None,
            )
            session.add(enrollment)
            session.flush()
            self._audit(session, "agent_enrollment.intent_created", now, enrollment)
        return IssuedEnrollmentIntent(enrollment, token)

    @staticmethod
    def _locked_enrollment(session: Session, token: EnrollmentToken) -> AgentEnrollment:
        enrollment = session.scalar(
            select(AgentEnrollment)
            .where(AgentEnrollment.public_id == token.identifier)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if enrollment is None or not hmac.compare_digest(
            enrollment.enrollment_digest, token.secret_digest
        ):
            raise EnrollmentRejected()
        return enrollment

    def exchange(
        self, token_value: object, *, expected_replacement_device_uuid: str | None = None
    ) -> EnrollmentExchange:
        try:
            token = EnrollmentToken.parse(token_value, expected_prefix="sbe1")
        except TokenRejected:
            raise EnrollmentRejected() from None
        with self.database.transaction() as session:
            enrollment = self._locked_enrollment(session, token)
            if expected_replacement_device_uuid is not None:
                if (
                    enrollment.mode != EnrollmentMode.REPLACE.value
                    or enrollment.replacement_device_id is None
                ):
                    raise EnrollmentRejected()
                replacement_uuid = session.scalar(
                    select(Device.device_uuid).where(Device.id == enrollment.replacement_device_id)
                )
                if replacement_uuid != expected_replacement_device_uuid:
                    raise EnrollmentRejected()
            now = database_utc(session)
            if enrollment.used_at is not None or enrollment.expires_at <= now:
                raise EnrollmentRejected()
            verification_token = EnrollmentToken.generate("sbv1", identifier=enrollment.public_id)
            device: Device
            credential: GeneratedCredential
            if enrollment.mode == EnrollmentMode.NEW.value:
                if (
                    enrollment.project_id is None
                    or enrollment.device_name is None
                    or enrollment.gpu_monitoring_enabled is None
                    or enrollment.expected_gpu_min_count is None
                ):
                    raise RuntimeError("Enrollment target violates its durable contract.")
                project = session.scalar(
                    select(Project)
                    .where(Project.id == enrollment.project_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if project is None:
                    raise NotFound("Project not found.")
                created = self.identity.enroll_in_session(
                    session,
                    project.public_id,
                    enrollment.device_name,
                    policy=GPUPolicy(
                        monitoring_enabled=enrollment.gpu_monitoring_enabled,
                        min_count=enrollment.expected_gpu_min_count,
                    ),
                    now=now,
                )
                device = created.device
                credential = created.credential
            elif enrollment.mode == EnrollmentMode.REPLACE.value:
                if enrollment.replacement_device_id is None:
                    raise RuntimeError("Enrollment target violates its durable contract.")
                replacement_device = session.scalar(
                    select(Device)
                    .where(Device.id == enrollment.replacement_device_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if replacement_device is None:
                    raise NotFound("Device not found.")
                device = replacement_device
                credential = self.identity.rotate_in_session(
                    session, device.device_uuid, overlap_hours=1, now=now
                )
            else:
                raise RuntimeError("Enrollment mode violates its durable contract.")
            enrollment.used_at = now
            enrollment.issued_device_id = device.id
            enrollment.verification_digest = verification_token.secret_digest
            enrollment.verification_expires_at = now + self.verification_lifetime
            self._audit(session, "agent_enrollment.exchanged", now, enrollment)
        return EnrollmentExchange(device, credential, verification_token)

    def verify_receipt(self, token_value: object) -> ReceiptVerification:
        try:
            token = EnrollmentToken.parse(token_value, expected_prefix="sbv1")
        except TokenRejected:
            raise ReceiptRejected() from None
        with self.database.transaction() as session:
            enrollment = session.scalar(
                select(AgentEnrollment).where(AgentEnrollment.public_id == token.identifier)
            )
            now = database_utc(session)
            if (
                enrollment is None
                or enrollment.verification_digest is None
                or enrollment.verification_expires_at is None
                or enrollment.used_at is None
                or enrollment.issued_device_id is None
                or enrollment.verification_expires_at <= now
                or not hmac.compare_digest(enrollment.verification_digest, token.secret_digest)
            ):
                raise ReceiptRejected()
            device = session.scalar(select(Device).where(Device.id == enrollment.issued_device_id))
            if device is None:
                raise ReceiptRejected()
            return ReceiptVerification(
                accepted_heartbeat=device.last_seen_at is not None
                and device.last_seen_at >= enrollment.used_at
            )

    @staticmethod
    def _enrollment(
        session: Session, enrollment_id: str, *, locked: bool = False
    ) -> AgentEnrollment:
        statement = select(AgentEnrollment).where(AgentEnrollment.public_id == enrollment_id)
        if locked:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        enrollment = session.scalar(statement)
        if enrollment is None:
            raise NotFound("Enrollment was not found.")
        return enrollment

    @staticmethod
    def _was_revoked(session: Session, enrollment: AgentEnrollment) -> bool:
        return (
            session.scalar(
                select(AuditEvent.id)
                .where(
                    AuditEvent.action == "agent_enrollment.revoked",
                    AuditEvent.details["enrollment_id"].as_string() == enrollment.public_id,
                )
                .limit(1)
            )
            is not None
        )

    def _status(
        self, session: Session, enrollment: AgentEnrollment, now: datetime
    ) -> EnrollmentStatus:
        if enrollment.used_at is None:
            state = (
                EnrollmentLifecycle.REVOKED
                if self._was_revoked(session, enrollment)
                else EnrollmentLifecycle.EXPIRED
                if enrollment.expires_at <= now
                else EnrollmentLifecycle.PENDING
            )
            return EnrollmentStatus(
                enrollment_id=enrollment.public_id,
                state=state,
                expires_at=enrollment.expires_at,
                device_id=None,
                last_seen_at=None,
            )
        device = (
            session.scalar(select(Device).where(Device.id == enrollment.issued_device_id))
            if enrollment.issued_device_id is not None
            else None
        )
        if device is None:
            raise NotFound("Enrollment device was not found.")
        return EnrollmentStatus(
            enrollment_id=enrollment.public_id,
            state=(
                EnrollmentLifecycle.ONLINE
                if device.last_seen_at is not None
                and device.last_seen_at >= now - self.offline_after
                else EnrollmentLifecycle.ENROLLED
            ),
            expires_at=enrollment.expires_at,
            device_id=device.device_uuid,
            last_seen_at=device.last_seen_at,
        )

    def status(self, enrollment_id: str) -> EnrollmentStatus:
        with self.database.transaction() as session:
            enrollment = self._enrollment(session, enrollment_id)
            return self._status(session, enrollment, database_utc(session))

    def revoke_unused(self, enrollment_id: str) -> EnrollmentStatus:
        with self.database.transaction() as session:
            enrollment = self._enrollment(session, enrollment_id, locked=True)
            now = database_utc(session)
            if enrollment.used_at is not None:
                raise Conflict("Enrollment has already issued a device credential.")
            if enrollment.expires_at <= now:
                raise Conflict("Enrollment is no longer valid.")
            enrollment.expires_at = now
            self._audit(session, "agent_enrollment.revoked", now, enrollment)
            return self._status(session, enrollment, now)
