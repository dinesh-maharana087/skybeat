"""Durable OWNER/ADMIN project notification configuration."""

from sqlalchemy import delete, select

from app.db import Database, database_utc
from app.models import (
    AuditEvent,
    Project,
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)
from app.schemas.notifications import ProjectNotificationUpdateRequest


class NotificationProjectNotFound(ValueError):
    pass


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
