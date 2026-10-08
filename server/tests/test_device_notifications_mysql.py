"""Stage 12D management and event snapshots on isolated MySQL 8/InnoDB."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db import database_utc
from app.health.service import AvailabilityService
from app.models import (
    AlertEvent,
    ApplicationUser,
    Device,
    NotificationDelivery,
    ProjectNotificationRecipient,
    ProjectNotificationSettings,
)
from app.notifications.configuration import snapshot_device_email_recipients
from app.notifications.management import (
    NotificationDeviceNotFound,
    NotificationManagementService,
    NotificationRecipientUnavailable,
)
from app.schemas.notifications import (
    DeviceNotificationUpdateRequest,
    ProjectNotificationUpdateRequest,
)

pytestmark = pytest.mark.mysql


def _policy(*, recipients: list[str], offline: bool = True) -> DeviceNotificationUpdateRequest:
    return DeviceNotificationUpdateRequest(
        recipients=recipients,
        device_offline_enabled=offline,
        device_recovered_enabled=True,
        gpu_degraded_enabled=True,
        gpu_recovered_enabled=True,
    )


def _user(database, email: str, *, active: bool = True) -> None:
    with database.transaction() as session:
        now = database_utc(session)
        session.add(
            ApplicationUser(
                email=email,
                display_name=email.split("@", 1)[0],
                google_sub=None,
                role="USER",
                is_active=active,
                created_at=now,
                updated_at=now,
            )
        )


def _project_policy(database, project_id: int, recipients: tuple[str, ...]) -> None:
    with database.transaction() as session:
        now = database_utc(session)
        session.add(
            ProjectNotificationSettings(
                project_id=project_id,
                device_offline_enabled=True,
                device_recovered_enabled=True,
                gpu_degraded_enabled=True,
                gpu_recovered_enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.add_all(
            [
                ProjectNotificationRecipient(
                    project_id=project_id, email=email, created_at=now, updated_at=now
                )
                for email in recipients
            ]
        )


def test_device_override_inherits_replaces_and_resets_without_copying_project(
    identity, mysql_database
):
    tag = uuid4().hex[:8]
    alice, bob, charlie, david = (
        f"{name}-{tag}@example.test" for name in ("alice", "bob", "charlie", "david")
    )
    project = identity.create_project(f"12D routing {tag}")
    other = identity.create_project(f"12D other {tag}")
    first = identity.enroll(project.public_id, "Inherited device")
    second = identity.enroll(project.public_id, "Custom device")
    _project_policy(mysql_database, project.id, (alice, bob))
    _user(mysql_database, charlie)
    _user(mysql_database, david)
    inactive = f"inactive-{tag}@example.test"
    _user(mysql_database, inactive, active=False)
    manager = NotificationManagementService(mysql_database, actor="owner@example.test")

    initial = manager.list_devices(project.public_id, legacy_recipients=("legacy@example.test",))
    by_id = {item["device_id"]: item for item in initial["items"]}
    assert by_id[first.device.device_uuid]["mode"] == "INHERIT_PROJECT"
    assert by_id[first.device.device_uuid]["effective"]["recipients"] == sorted((alice, bob))

    manager.update_device(
        project.public_id, second.device.device_uuid, _policy(recipients=[charlie])
    )
    with pytest.raises(NotificationRecipientUnavailable):
        manager.update_device(
            project.public_id, second.device.device_uuid, _policy(recipients=[charlie, inactive])
        )
    with pytest.raises(NotificationDeviceNotFound):
        manager.update_device(other.public_id, second.device.device_uuid, _policy(recipients=[]))
    manager.update_project(
        project.public_id,
        ProjectNotificationUpdateRequest(
            recipients=[alice, david],
            device_offline_enabled=True,
            device_recovered_enabled=True,
            gpu_degraded_enabled=True,
            gpu_recovered_enabled=True,
        ),
    )
    changed = manager.list_devices(project.public_id, legacy_recipients=("legacy@example.test",))
    by_id = {item["device_id"]: item for item in changed["items"]}
    assert by_id[first.device.device_uuid]["effective"]["recipients"] == sorted((alice, david))
    assert by_id[second.device.device_uuid]["effective"]["recipients"] == [charlie]
    assert by_id[second.device.device_uuid]["mode"] == "CUSTOM"

    manager.update_device(project.public_id, second.device.device_uuid, _policy(recipients=[]))
    zero = manager.list_devices(project.public_id, legacy_recipients=("legacy@example.test",))
    assert (
        next(item for item in zero["items"] if item["device_id"] == second.device.device_uuid)[
            "effective"
        ]["recipients"]
        == []
    )
    manager.reset_device(project.public_id, second.device.device_uuid)
    inherited = manager.list_devices(project.public_id, legacy_recipients=("legacy@example.test",))
    restored = next(
        item for item in inherited["items"] if item["device_id"] == second.device.device_uuid
    )
    assert restored["mode"] == "INHERIT_PROJECT"
    assert restored["effective"]["recipients"] == sorted((alice, david))


def test_device_routing_is_snapshotted_when_offline_and_recovery_events_are_created(
    identity, mysql_database
):
    tag = uuid4().hex[:8]
    project = identity.create_project(f"12D snapshot {tag}")
    enrolled = identity.enroll(project.public_id, "Snapshot device")
    charlie, david = f"charlie-{tag}@example.test", f"david-{tag}@example.test"
    _project_policy(mysql_database, project.id, (f"project-{tag}@example.test",))
    _user(mysql_database, charlie)
    _user(mysql_database, david)
    manager = NotificationManagementService(mysql_database, actor="owner@example.test")
    manager.update_device(
        project.public_id, enrolled.device.device_uuid, _policy(recipients=[charlie])
    )
    with mysql_database.transaction() as session:
        device = session.get(Device, enrolled.device.id, with_for_update=True)
        assert device is not None
        device.monitoring_started_at = database_utc(session) - timedelta(seconds=180)
        device.last_seen_at = None
        device.availability_state = "ONLINE"
    service = AvailabilityService(mysql_database, email_recipients=("legacy@example.test",))
    service.sweep()
    manager.update_device(
        project.public_id, enrolled.device.device_uuid, _policy(recipients=[david])
    )
    with mysql_database.transaction() as session:
        device = session.get(Device, enrolled.device.id, with_for_update=True)
        assert device is not None
        service.accept_heartbeat(session, device, database_utc(session))
    with mysql_database.transaction() as session:
        deliveries = session.execute(
            select(AlertEvent.event_kind, NotificationDelivery.destination_snapshot)
            .join(NotificationDelivery, NotificationDelivery.event_id == AlertEvent.id)
            .where(AlertEvent.device_id == enrolled.device.id)
        ).all()
    assert sorted(deliveries) == sorted([("DEVICE_OFFLINE", charlie), ("DEVICE_RECOVERED", david)])


def test_database_resolution_preserves_global_fallback_and_explicit_empty_policy(
    identity, mysql_database
):
    tag = uuid4().hex[:8]
    project = identity.create_project(f"12D empty {tag}")
    enrolled = identity.enroll(project.public_id, "Empty route device")
    charlie = f"charlie-{tag}@example.test"
    _user(mysql_database, charlie)
    manager = NotificationManagementService(mysql_database, actor="admin@example.test")
    legacy = ("legacy@example.test",)

    def resolved(kind: str) -> tuple[str, ...]:
        with mysql_database.transaction() as session:
            return snapshot_device_email_recipients(
                session,
                device_id=enrolled.device.id,
                project_id=project.id,
                event_kind=kind,
                legacy_recipients=legacy,
            )

    assert resolved("DEVICE_OFFLINE") == legacy
    _project_policy(mysql_database, project.id, ())
    assert resolved("DEVICE_OFFLINE") == ()
    manager.update_device(
        project.public_id,
        enrolled.device.device_uuid,
        _policy(recipients=[charlie], offline=False),
    )
    assert resolved("DEVICE_OFFLINE") == ()
    assert resolved("DEVICE_RECOVERED") == (charlie,)
    manager.update_device(project.public_id, enrolled.device.device_uuid, _policy(recipients=[]))
    assert resolved("DEVICE_RECOVERED") == ()
    manager.reset_device(project.public_id, enrolled.device.device_uuid)
    assert resolved("DEVICE_OFFLINE") == ()
