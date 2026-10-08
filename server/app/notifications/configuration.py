"""Project defaults, device overrides, and event-time recipient selection."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DeviceNotificationRecipient,
    DeviceNotificationSettings,
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)
from app.users.service import normalize_email


@dataclass(frozen=True)
class EventNotificationSettings:
    """Persisted event controls; a present instance means a project is configured."""

    device_offline_enabled: bool
    device_recovered_enabled: bool
    gpu_degraded_enabled: bool
    gpu_recovered_enabled: bool

    def enabled_for(self, event_kind: str) -> bool:
        return {
            "DEVICE_OFFLINE": self.device_offline_enabled,
            "DEVICE_RECOVERED": self.device_recovered_enabled,
            "GPU_DEGRADED": self.gpu_degraded_enabled,
            "GPU_RECOVERED": self.gpu_recovered_enabled,
        }.get(event_kind, False)


@dataclass(frozen=True)
class ResolvedEmailPolicy:
    source: str
    settings: EventNotificationSettings | None
    recipients: tuple[str, ...]


def _normalized(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({normalize_email(value) for value in values}))


def select_email_policy(
    *,
    project_settings: EventNotificationSettings | None,
    project_recipients: tuple[str, ...],
    legacy_recipients: tuple[str, ...],
    device_settings: EventNotificationSettings | None = None,
    device_recipients: tuple[str, ...] = (),
) -> ResolvedEmailPolicy:
    """Expose the same device > project > deployment precedence to reads and events."""

    if device_settings is not None:
        return ResolvedEmailPolicy("DEVICE", device_settings, _normalized(device_recipients))
    if project_settings is not None:
        return ResolvedEmailPolicy("PROJECT", project_settings, _normalized(project_recipients))
    return ResolvedEmailPolicy("GLOBAL", None, _normalized(legacy_recipients))


def resolve_email_recipients(
    *,
    settings: EventNotificationSettings | None,
    recipients: tuple[str, ...],
    event_kind: str,
    legacy_recipients: tuple[str, ...],
    device_settings: EventNotificationSettings | None = None,
    device_recipients: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Choose one authoritative policy; explicit empty device routing never falls through."""

    policy = select_email_policy(
        project_settings=settings,
        project_recipients=recipients,
        device_settings=device_settings,
        device_recipients=device_recipients,
        legacy_recipients=legacy_recipients,
    )
    if policy.settings is not None and not policy.settings.enabled_for(event_kind):
        return ()
    return policy.recipients


def snapshot_project_email_recipients(
    session: Session, *, project_id: int, event_kind: str, legacy_recipients: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve once in the event transaction; delivery retries use their stored snapshot."""

    row = session.get(ProjectNotificationSettings, project_id)
    settings = (
        None
        if row is None
        else EventNotificationSettings(
            row.device_offline_enabled,
            row.device_recovered_enabled,
            row.gpu_degraded_enabled,
            row.gpu_recovered_enabled,
        )
    )
    recipients = tuple(
        session.scalars(
            select(ProjectNotificationRecipient.email).where(
                ProjectNotificationRecipient.project_id == project_id
            )
        )
    )
    return resolve_email_recipients(
        settings=settings,
        recipients=recipients,
        event_kind=event_kind,
        legacy_recipients=legacy_recipients,
    )


def snapshot_device_email_recipients(
    session: Session,
    *,
    device_id: int,
    project_id: int,
    event_kind: str,
    legacy_recipients: tuple[str, ...],
) -> tuple[str, ...]:
    """Resolve device override first, otherwise preserve the existing project path."""

    row = session.get(DeviceNotificationSettings, device_id)
    if row is None:
        return snapshot_project_email_recipients(
            session,
            project_id=project_id,
            event_kind=event_kind,
            legacy_recipients=legacy_recipients,
        )
    settings = EventNotificationSettings(
        row.device_offline_enabled,
        row.device_recovered_enabled,
        row.gpu_degraded_enabled,
        row.gpu_recovered_enabled,
    )
    recipients = tuple(
        session.scalars(
            select(DeviceNotificationRecipient.email).where(
                DeviceNotificationRecipient.device_id == device_id
            )
        )
    )
    return resolve_email_recipients(
        settings=None,
        recipients=(),
        device_settings=settings,
        device_recipients=recipients,
        event_kind=event_kind,
        legacy_recipients=legacy_recipients,
    )
