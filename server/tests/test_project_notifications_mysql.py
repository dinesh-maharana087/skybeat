"""Real-MySQL Stage 11 recipient snapshot and fallback policy coverage."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import database_utc
from app.health.service import AvailabilityService
from app.models import (
    AlertEvent,
    Device,
    NotificationDelivery,
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)

pytestmark = pytest.mark.mysql


def _make_offline(database, device_id: int) -> None:
    with database.transaction() as session:
        device = session.get(Device, device_id)
        assert device is not None
        device.monitoring_started_at = database_utc(session) - timedelta(seconds=180)
        device.last_seen_at = None
        device.availability_state = "ONLINE"


def test_project_policy_snapshots_events_without_merging_legacy_recipients(
    identity, mysql_database
):
    project = identity.create_project("Notification policy")
    enrolled = identity.enroll(project.public_id, "Notification policy device")
    with mysql_database.transaction() as session:
        now = database_utc(session)
        session.add(
            ProjectNotificationSettings(
                project_id=project.id,
                device_offline_enabled=True,
                device_recovered_enabled=True,
                gpu_degraded_enabled=True,
                gpu_recovered_enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ProjectNotificationRecipient(
                project_id=project.id,
                email="first@example.test",
                created_at=now,
                updated_at=now,
            )
        )
    _make_offline(mysql_database, enrolled.device.id)
    service = AvailabilityService(mysql_database, email_recipients=("legacy@example.test",))

    service.sweep()

    with mysql_database.transaction() as session:
        offline = session.scalar(
            select(NotificationDelivery)
            .join(AlertEvent, NotificationDelivery.event_id == AlertEvent.id)
            .where(AlertEvent.event_kind == "DEVICE_OFFLINE")
        )
        assert offline is not None
        assert offline.destination_snapshot == "first@example.test"
        session.execute(
            ProjectNotificationRecipient.__table__.delete().where(
                ProjectNotificationRecipient.project_id == project.id
            )
        )
        now = database_utc(session)
        session.add(
            ProjectNotificationRecipient(
                project_id=project.id,
                email="second@example.test",
                created_at=now,
                updated_at=now,
            )
        )
        device = session.scalar(
            select(Device).where(Device.id == enrolled.device.id).with_for_update()
        )
        assert device is not None
        service.accept_heartbeat(session, device, now)

    with mysql_database.transaction() as session:
        deliveries = session.scalars(
            select(NotificationDelivery)
            .join(AlertEvent, NotificationDelivery.event_id == AlertEvent.id)
            .order_by(NotificationDelivery.id)
        ).all()
        assert [delivery.destination_snapshot for delivery in deliveries] == [
            "first@example.test",
            "second@example.test",
        ]
        assert all(
            delivery.destination_snapshot != "legacy@example.test" for delivery in deliveries
        )


def test_configured_project_with_no_recipients_creates_no_email_delivery(identity, mysql_database):
    project = identity.create_project("No recipients")
    enrolled = identity.enroll(project.public_id, "No recipients device")
    with mysql_database.transaction() as session:
        now = database_utc(session)
        session.add(
            ProjectNotificationSettings(
                project_id=project.id,
                device_offline_enabled=True,
                device_recovered_enabled=True,
                gpu_degraded_enabled=True,
                gpu_recovered_enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
    _make_offline(mysql_database, enrolled.device.id)

    AvailabilityService(mysql_database, email_recipients=("legacy@example.test",)).sweep()

    with mysql_database.transaction() as session:
        assert session.scalars(select(AlertEvent)).one().event_kind == "DEVICE_OFFLINE"
        assert session.scalars(select(NotificationDelivery)).all() == []
