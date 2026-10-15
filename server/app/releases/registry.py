"""Durable release approval and one active installation selection."""

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import Database, database_utc
from app.models import AgentReleaseSelection, AuditEvent, RegisteredAgentRelease
from app.releases.managed import ReleaseStore, StoredRelease
from app.releases.service import ReleaseMetadata, ReleaseUnavailable


class ReleaseConflict(ValueError):
    """A version already identifies other immutable bytes."""


def _time(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value is not None else None


class ManagedReleaseService:
    def __init__(self, database: Database, store_root: Path | None, server_url: str) -> None:
        self.database = database
        self.store = ReleaseStore(store_root, server_url)

    def _checked(self, row: RegisteredAgentRelease) -> StoredRelease:
        artifact = self.store.validate(row.archive_sha256)
        if artifact.version != row.version or artifact.wheel_sha256 != row.wheel_sha256:
            raise ReleaseUnavailable("Registered release identity does not match stored bytes.")
        return artifact

    @staticmethod
    def _audit(
        session: object,
        actor: str,
        action: str,
        now: datetime,
        digest: str,
        previous_digest: str | None = None,
    ) -> None:
        details = {"archive_sha256": digest}
        if previous_digest is not None:
            details["previous_archive_sha256"] = previous_digest
        session.add(  # type: ignore[attr-defined]
            AuditEvent(
                actor=actor,
                action=action,
                project_id=None,
                device_id=None,
                occurred_at=now,
                details=details,
            )
        )

    def register(self, name: str, actor: str) -> dict[str, object]:
        artifact = self.store.import_candidate(name)
        try:
            with self.database.transaction() as session:
                existing = session.get(RegisteredAgentRelease, artifact.archive_sha256)
                selection = session.get(AgentReleaseSelection, 1)
                if existing is not None:
                    self._checked(existing)
                    active = (
                        selection is not None
                        and selection.archive_sha256 == artifact.archive_sha256
                    )
                    return self._view(existing, active, True, selection=selection)
                same_version = session.scalar(
                    select(RegisteredAgentRelease).where(
                        RegisteredAgentRelease.version == artifact.version
                    )
                )
                if same_version is not None:
                    raise ReleaseConflict("This version already identifies a registered artifact.")
                now = database_utc(session)
                row = RegisteredAgentRelease(
                    archive_sha256=artifact.archive_sha256,
                    version=artifact.version,
                    wheel_sha256=artifact.wheel_sha256,
                    status="VERIFIED",
                    registered_by=actor,
                    registered_at=now,
                    verified_at=now,
                    approved_by=None,
                    approved_at=None,
                )
                session.add(row)
                self._audit(
                    session, actor, "agent_release.registered", now, artifact.archive_sha256
                )
                return self._view(row, False, True)
        except IntegrityError as exc:
            if getattr(exc.orig, "args", (None,))[0] == 1062:
                raise ReleaseConflict(
                    "This version already identifies a registered artifact."
                ) from exc
            raise

    def verify(self, digest: str, actor: str) -> dict[str, object]:
        with self.database.transaction() as session:
            row = session.get(RegisteredAgentRelease, digest)
            if row is None:
                raise ReleaseUnavailable("Registered release was not found.")
            self._checked(row)
            row.verified_at = now = database_utc(session)
            active = session.get(AgentReleaseSelection, 1)
            self._audit(session, actor, "agent_release.verified", now, digest)
            return self._view(
                row,
                active is not None and active.archive_sha256 == digest,
                True,
                selection=active,
            )

    def activate(self, digest: str, actor: str) -> dict[str, object]:
        with self.database.transaction() as session:
            selection = session.scalar(
                select(AgentReleaseSelection).where(AgentReleaseSelection.id == 1).with_for_update()
            )
            if selection is None:
                raise ReleaseUnavailable("Release selection storage is unavailable.")
            row = session.get(RegisteredAgentRelease, digest)
            if row is None or row.status not in {"VERIFIED", "APPROVED"}:
                raise ReleaseUnavailable("Registered release is not eligible for activation.")
            self._checked(row)
            now = database_utc(session)
            if row.approved_at is None:
                row.approved_at = now
                row.approved_by = actor
            row.status = "APPROVED"
            previous_digest = selection.archive_sha256
            selection.archive_sha256 = digest
            selection.activated_by = actor
            selection.activated_at = now
            self._audit(session, actor, "agent_release.activated", now, digest, previous_digest)
            return self._view(row, True, True, selection=selection)

    @staticmethod
    def _view(
        row: RegisteredAgentRelease,
        active: bool,
        available: bool,
        availability_error: str | None = None,
        selection: AgentReleaseSelection | None = None,
    ) -> dict[str, object]:
        return {
            "version": row.version,
            "archive_sha256": row.archive_sha256,
            "wheel_sha256": row.wheel_sha256,
            "status": row.status,
            "active": active,
            "available": available,
            "availability_error": availability_error,
            "registered_by": row.registered_by,
            "registered_at": _time(row.registered_at),
            "verified_at": _time(row.verified_at),
            "approved_by": row.approved_by,
            "approved_at": _time(row.approved_at),
            "activated_by": selection.activated_by if active and selection is not None else None,
            "activated_at": _time(selection.activated_at)
            if active and selection is not None
            else None,
        }

    def list(self) -> list[dict[str, object]]:
        with self.database.transaction() as session:
            rows = list(
                session.scalars(
                    select(RegisteredAgentRelease).order_by(
                        RegisteredAgentRelease.registered_at.desc()
                    )
                )
            )
            selection = session.get(AgentReleaseSelection, 1)
            result = []
            for row in rows:
                try:
                    self._checked(row)
                    available = True
                    error = None
                except ReleaseUnavailable as exc:
                    available = False
                    error = str(exc)
                result.append(
                    self._view(
                        row,
                        selection is not None and selection.archive_sha256 == row.archive_sha256,
                        available,
                        error,
                        selection,
                    )
                )
            return result

    def active_artifact(self) -> StoredRelease:
        with self.database.transaction() as session:
            selection = session.get(AgentReleaseSelection, 1)
            if selection is None or selection.archive_sha256 is None:
                raise ReleaseUnavailable("No approved installation release is active.")
            row = session.get(RegisteredAgentRelease, selection.archive_sha256)
            if row is None or row.status != "APPROVED":
                raise ReleaseUnavailable("Active release approval is unavailable.")
            return self._checked(row)

    def current(self) -> ReleaseMetadata:
        return self.active_artifact().metadata

    def archive(self) -> Path:
        return self.active_artifact().archive

    def archive_by_digest(self, archive_sha256: str) -> Path:
        """Serve an approved immutable artifact even if a newer release becomes active."""
        with self.database.transaction() as session:
            row = session.get(RegisteredAgentRelease, archive_sha256)
            if row is None or row.status != "APPROVED":
                raise ReleaseUnavailable("Pinned release is unavailable.")
            return self._checked(row).archive

    def archive_for(self, version: str, wheel_sha256: str, archive_sha256: str | None) -> Path:
        if archive_sha256 is None:
            raise ReleaseUnavailable("Pinned archive identity is missing.")
        with self.database.transaction() as session:
            row = session.get(RegisteredAgentRelease, archive_sha256)
            if row is None or row.status != "APPROVED":
                raise ReleaseUnavailable("Pinned release is unavailable.")
            artifact = self._checked(row)
            if artifact.version != version or artifact.wheel_sha256 != wheel_sha256:
                raise ReleaseUnavailable("Pinned release identity is invalid.")
            return artifact.archive
