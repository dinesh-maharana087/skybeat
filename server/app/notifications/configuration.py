"""Project-scoped notification policy and event-time recipient selection."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProjectNotificationRecipient, ProjectNotificationSettings
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


def _normalized(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({normalize_email(value) for value in values}))


def resolve_email_recipients(
    *,
    settings: EventNotificationSettings | None,
    recipients: tuple[str, ...],
    event_kind: str,
    legacy_recipients: tuple[str, ...],
) -> tuple[str, ...]:
    """Snapshot configured recipients or use legacy values only before first configuration."""

    if settings is None:
        return _normalized(legacy_recipients)
    if not settings.enabled_for(event_kind):
        return ()
    return _normalized(recipients)


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
