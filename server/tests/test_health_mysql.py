"""Real-MySQL availability and incident lifecycle coverage."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from test_heartbeat_api import sample

from app.db import database_utc
from app.health.service import AvailabilityService
from app.heartbeats.service import HeartbeatService
from app.models import AlertEvent, Device, Incident, NotificationDelivery
from app.schemas.heartbeat import parse_heartbeat

pytestmark = pytest.mark.mysql


def _age_device(mysql_database, device_id, seconds):
    with mysql_database.transaction() as session:
        device = session.get(Device, device_id)
        assert device is not None
        now = database_utc(session)
        device.monitoring_started_at = now - timedelta(seconds=seconds)
        device.last_seen_at = None
        device.availability_state = "ONLINE"
        return now


def test_sweep_opens_one_offline_incident_event_and_email_delivery(identity, mysql_database):
    project = identity.create_project("Availability")
    enrolled = identity.enroll(project.public_id, "Offline device")
    _age_device(mysql_database, enrolled.device.id, 180)
    service = AvailabilityService(mysql_database, email_recipients=("ops@example.test",))

    service.sweep()
    service.sweep()

    with mysql_database.transaction() as session:
        device = session.get(Device, enrolled.device.id)
        assert device is not None
        assert device.availability_state == "OFFLINE"
        assert (
            session.scalar(
                select(func.count()).select_from(Incident).where(Incident.device_id == device.id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AlertEvent)
                .where(AlertEvent.device_id == device.id, AlertEvent.event_kind == "DEVICE_OFFLINE")
            )
            == 1
        )
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery is not None
        assert delivery.status == "PENDING"
        assert delivery.destination_snapshot == "ops@example.test"


def test_late_heartbeat_preserves_offline_then_recovery(identity, mysql_database):
    project = identity.create_project("Availability")
    enrolled = identity.enroll(project.public_id, "Late heartbeat")
    service = AvailabilityService(mysql_database, email_recipients=("ops@example.test",))
    _age_device(mysql_database, enrolled.device.id, 180)

    with mysql_database.transaction() as session:
        device = session.scalar(
            select(Device).where(Device.id == enrolled.device.id).with_for_update()
        )
        assert device is not None
        service.accept_heartbeat(session, device, database_utc(session))

    with mysql_database.transaction() as session:
        device = session.get(Device, enrolled.device.id)
        assert device is not None
        assert device.availability_state == "ONLINE"
        incident = session.scalar(select(Incident).where(Incident.device_id == device.id))
        assert incident is not None
        assert incident.closed_at is not None
        assert session.scalars(
            select(AlertEvent.event_kind)
            .where(AlertEvent.incident_id == incident.id)
            .order_by(AlertEvent.id)
        ).all() == ["DEVICE_OFFLINE", "DEVICE_RECOVERED"]
        offline_delivery = session.scalar(
            select(NotificationDelivery)
            .join(AlertEvent, NotificationDelivery.event_id == AlertEvent.id)
            .where(AlertEvent.event_kind == "DEVICE_OFFLINE")
        )
        assert offline_delivery is not None
        assert offline_delivery.status == "CANCELLED"
        assert offline_delivery.cancel_reason == "superseded_by_recovery"


def test_recovery_then_later_outage_creates_a_new_incident(identity, mysql_database):
    project = identity.create_project("Availability")
    enrolled = identity.enroll(project.public_id, "Second outage")
    service = AvailabilityService(mysql_database)
    _age_device(mysql_database, enrolled.device.id, 180)
    service.sweep()

    with mysql_database.transaction() as session:
        device = session.scalar(
            select(Device).where(Device.id == enrolled.device.id).with_for_update()
        )
        assert device is not None
        service.accept_heartbeat(session, device, database_utc(session))
        device.last_seen_at = database_utc(session) - timedelta(seconds=180)
    service.sweep()

    with mysql_database.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Incident)
                .where(Incident.device_id == enrolled.device.id)
            )
            == 2
        )


def test_heartbeat_ingestion_reconciles_late_outage_before_updating_last_seen(
    identity, mysql_database
):
    project = identity.create_project("Availability")
    enrolled = identity.enroll(project.public_id, "Ingestion recovery")
    _age_device(mysql_database, enrolled.device.id, 180)
    heartbeat = parse_heartbeat(json.dumps(sample(enrolled.device.device_uuid)).encode())
    service = HeartbeatService(
        mysql_database,
        allowed=lambda _: True,
        email_recipients=("ops@example.test",),
    )

    service.accept(heartbeat, enrolled.credential.token.get_secret_value())

    with mysql_database.transaction() as session:
        assert session.scalars(select(AlertEvent.event_kind).order_by(AlertEvent.id)).all() == [
            "DEVICE_OFFLINE",
            "DEVICE_RECOVERED",
        ]


def test_concurrent_sweeps_create_one_incident_and_one_offline_event(identity, mysql_database):
    project = identity.create_project("Availability")
    enrolled = identity.enroll(project.public_id, "Concurrent sweep")
    _age_device(mysql_database, enrolled.device.id, 180)
    service = AvailabilityService(mysql_database)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: service.sweep(), range(2)))

    with mysql_database.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Incident)
                .where(Incident.device_id == enrolled.device.id)
            )
            == 1
        )


def test_failed_availability_commit_rolls_back_state_incident_and_event(identity, mysql_database):
    project = identity.create_project("Availability")
    enrolled = identity.enroll(project.public_id, "Rollback")
    _age_device(mysql_database, enrolled.device.id, 180)

    commits = 0

    def fail_commit(connection):
        nonlocal commits
        commits += 1
        if commits == 2:
            raise OperationalError("commit", {}, Exception("sensitive-detail"))

    event.listen(mysql_database.engine, "commit", fail_commit)
    try:
        with pytest.raises(OperationalError):
            AvailabilityService(mysql_database).sweep()
    finally:
        event.remove(mysql_database.engine, "commit", fail_commit)

    with mysql_database.transaction() as session:
        device = session.get(Device, enrolled.device.id)
        assert device is not None
        assert device.availability_state == "ONLINE"
        assert (
            session.scalar(
                select(func.count()).select_from(Incident).where(Incident.device_id == device.id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AlertEvent)
                .where(
                    AlertEvent.device_id == enrolled.device.id,
                    AlertEvent.event_kind == "DEVICE_OFFLINE",
                )
            )
            == 1
        )
