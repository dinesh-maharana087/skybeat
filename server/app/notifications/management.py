"""Durable OWNER/ADMIN project defaults and device overrides."""

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import Database, database_utc
from app.models import (
    ApplicationUser,
    AuditEvent,
    Device,
    DeviceNotificationRecipient,
    DeviceNotificationSettings,
    Project,
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)
from app.notifications.configuration import EventNotificationSettings, select_email_policy
from app.schemas.notifications import (
    DeviceNotificationUpdateRequest,
    ProjectNotificationUpdateRequest,
)


class NotificationProjectNotFound(ValueError):
    pass


class NotificationDeviceNotFound(ValueError):
    pass


class NotificationRecipientUnavailable(ValueError):
    pass


def _settings(
    row: ProjectNotificationSettings | DeviceNotificationSettings | None,
) -> EventNotificationSettings | None:
    if row is None:
        return None
    return EventNotificationSettings(
        row.device_offline_enabled,
        row.device_recovered_enabled,
        row.gpu_degraded_enabled,
        row.gpu_recovered_enabled,
    )


def _policy_projection(
    settings: EventNotificationSettings | None, recipients: tuple[str, ...]
) -> dict[str, object]:
    return {
        "recipients": list(recipients),
        "device_offline_enabled": settings.device_offline_enabled if settings else True,
        "device_recovered_enabled": settings.device_recovered_enabled if settings else True,
        "gpu_degraded_enabled": settings.gpu_degraded_enabled if settings else True,
        "gpu_recovered_enabled": settings.gpu_recovered_enabled if settings else True,
    }


class NotificationManagementService:
    def __init__(self, database: Database, *, actor: str) -> None:
        self.database = database
        self.actor = actor

    def list_projects(self) -> dict[str, object]:
        with self.database.transaction() as session:
            rows = session.scalars(select(Project).order_by(Project.name, Project.public_id)).all()
            items = []
            for project in rows:
                settings = session.get(ProjectNotificationSettings, project.id)
                recipients = session.scalars(
                    select(ProjectNotificationRecipient.email)
                    .where(ProjectNotificationRecipient.project_id == project.id)
                    .order_by(ProjectNotificationRecipient.email)
                ).all()
                items.append(
                    {
                        "project_id": project.public_id,
                        "project_name": project.name,
                        "configured": settings is not None,
                        "recipients": list(recipients),
                        "device_offline_enabled": settings.device_offline_enabled
                        if settings
                        else True,
                        "device_recovered_enabled": settings.device_recovered_enabled
                        if settings
                        else True,
                        "gpu_degraded_enabled": settings.gpu_degraded_enabled if settings else True,
                        "gpu_recovered_enabled": settings.gpu_recovered_enabled
                        if settings
                        else True,
                    }
                )
            return {"items": items}

    def update_project(
        self, project_uuid: str, payload: ProjectNotificationUpdateRequest
    ) -> dict[str, object]:
        with self.database.transaction() as session:
            project = session.scalar(
                select(Project).where(Project.public_id == project_uuid).with_for_update()
            )
            if project is None:
                raise NotificationProjectNotFound()
            now = database_utc(session)
            settings = session.get(ProjectNotificationSettings, project.id)
            if settings is None:
                settings = ProjectNotificationSettings(
                    project_id=project.id,
                    created_at=now,
                    updated_at=now,
                    **payload.model_dump(exclude={"recipients"}),
                )
                session.add(settings)
            else:
                for name, value in payload.model_dump(exclude={"recipients"}).items():
                    setattr(settings, name, value)
                settings.updated_at = now
            session.execute(
                delete(ProjectNotificationRecipient).where(
                    ProjectNotificationRecipient.project_id == project.id
                )
            )
            session.add_all(
                [
                    ProjectNotificationRecipient(
                        project_id=project.id,
                        email=email,
                        created_at=now,
                        updated_at=now,
                    )
                    for email in payload.recipients
                ]
            )
            session.add(
                AuditEvent(
                    actor=self.actor,
                    action="notification.project_policy_updated",
                    project_id=project.id,
                    device_id=None,
                    occurred_at=now,
                    details={
                        "recipient_count": len(payload.recipients),
                        "device_offline_enabled": payload.device_offline_enabled,
                        "device_recovered_enabled": payload.device_recovered_enabled,
                        "gpu_degraded_enabled": payload.gpu_degraded_enabled,
                        "gpu_recovered_enabled": payload.gpu_recovered_enabled,
                    },
                )
            )
            return {
                "project_id": project.public_id,
                "configured": True,
                "recipients": payload.recipients,
            }

    @staticmethod
    def _project(session: Session, project_uuid: str) -> Project:
        project = session.scalar(select(Project).where(Project.public_id == project_uuid))
        if project is None:
            raise NotificationProjectNotFound()
        return project

    @staticmethod
    def _device(session: Session, project_id: int, device_uuid: str) -> Device:
        device = session.scalar(
            select(Device)
            .where(Device.device_uuid == device_uuid, Device.project_id == project_id)
            .with_for_update()
        )
        if device is None:
            raise NotificationDeviceNotFound()
        return device

    def list_devices(
        self, project_uuid: str, *, legacy_recipients: tuple[str, ...]
    ) -> dict[str, object]:
        with self.database.transaction() as session:
            project = self._project(session, project_uuid)
            project_settings = _settings(session.get(ProjectNotificationSettings, project.id))
            project_recipients = tuple(
                session.scalars(
                    select(ProjectNotificationRecipient.email).where(
                        ProjectNotificationRecipient.project_id == project.id
                    )
                )
            )
            inherited = select_email_policy(
                project_settings=project_settings,
                project_recipients=project_recipients,
                legacy_recipients=legacy_recipients,
            )
            devices = session.scalars(
                select(Device)
                .where(Device.project_id == project.id)
                .order_by(Device.name, Device.device_uuid)
            ).all()
            ids = [device.id for device in devices]
            overrides = {
                row.device_id: row
                for row in session.scalars(
                    select(DeviceNotificationSettings).where(
                        DeviceNotificationSettings.device_id.in_(ids)
                    )
                )
            }
            recipients_by_device: dict[int, list[str]] = defaultdict(list)
            for device_id, email in session.execute(
                select(DeviceNotificationRecipient.device_id, DeviceNotificationRecipient.email)
                .where(DeviceNotificationRecipient.device_id.in_(ids))
                .order_by(DeviceNotificationRecipient.email)
            ):
                recipients_by_device[device_id].append(email)
            items = []
            for device in devices:
                device_settings = _settings(overrides.get(device.id))
                device_recipients = tuple(recipients_by_device[device.id])
                policy = select_email_policy(
                    project_settings=project_settings,
                    project_recipients=project_recipients,
                    device_settings=device_settings,
                    device_recipients=device_recipients,
                    legacy_recipients=legacy_recipients,
                )
                items.append(
                    {
                        "device_id": device.device_uuid,
                        "device_name": device.name,
                        "project_id": project.public_id,
                        "project_name": project.name,
                        "mode": "CUSTOM" if device_settings is not None else "INHERIT_PROJECT",
                        "effective_source": policy.source,
                        "effective": _policy_projection(policy.settings, policy.recipients),
                        "inherited": _policy_projection(inherited.settings, inherited.recipients),
                        "custom": _policy_projection(device_settings, device_recipients)
                        if device_settings is not None
                        else None,
                    }
                )
            return {"project_id": project.public_id, "project_name": project.name, "items": items}

    def update_device(
        self, project_uuid: str, device_uuid: str, payload: DeviceNotificationUpdateRequest
    ) -> dict[str, object]:
        with self.database.transaction() as session:
            project = self._project(session, project_uuid)
            device = self._device(session, project.id, device_uuid)
            settings = session.get(DeviceNotificationSettings, device.id)
            existing = set(
                session.scalars(
                    select(DeviceNotificationRecipient.email).where(
                        DeviceNotificationRecipient.device_id == device.id
                    )
                )
            )
            new_addresses = set(payload.recipients) - existing
            if new_addresses:
                active = set(
                    session.scalars(
                        select(ApplicationUser.email).where(
                            ApplicationUser.email.in_(new_addresses),
                            ApplicationUser.is_active.is_(True),
                        )
                    )
                )
                if active != new_addresses:
                    raise NotificationRecipientUnavailable()
            now = database_utc(session)
            values = payload.model_dump(exclude={"recipients"})
            if settings is None:
                settings = DeviceNotificationSettings(
                    device_id=device.id, created_at=now, updated_at=now, **values
                )
                session.add(settings)
                session.flush()
            else:
                for name, value in values.items():
                    setattr(settings, name, value)
                settings.updated_at = now
            session.execute(
                delete(DeviceNotificationRecipient).where(
                    DeviceNotificationRecipient.device_id == device.id
                )
            )
            session.add_all(
                [
                    DeviceNotificationRecipient(
                        device_id=device.id, email=email, created_at=now, updated_at=now
                    )
                    for email in payload.recipients
                ]
            )
            session.add(
                AuditEvent(
                    actor=self.actor,
                    action="notification.device_policy_updated",
                    project_id=project.id,
                    device_id=device.id,
                    occurred_at=now,
                    details={"recipient_count": len(payload.recipients), **values},
                )
            )
            return {"device_id": device.device_uuid, "mode": "CUSTOM"}

    def reset_device(self, project_uuid: str, device_uuid: str) -> dict[str, object]:
        with self.database.transaction() as session:
            project = self._project(session, project_uuid)
            device = self._device(session, project.id, device_uuid)
            settings = session.get(DeviceNotificationSettings, device.id)
            if settings is not None:
                session.delete(settings)
                session.add(
                    AuditEvent(
                        actor=self.actor,
                        action="notification.device_policy_reset",
                        project_id=project.id,
                        device_id=device.id,
                        occurred_at=database_utc(session),
                        details={},
                    )
                )
            return {"device_id": device.device_uuid, "mode": "INHERIT_PROJECT"}
