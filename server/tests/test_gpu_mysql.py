"""Real-MySQL GPU lifecycle, notification and offline-reset coverage."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import database_utc
from app.gpu.service import GPUIncidentService
from app.health.service import AvailabilityService
from app.models import AlertEvent, Device, Incident, NotificationDelivery

pytestmark = pytest.mark.mysql


def _sample(state: str, *, gpus: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "gpu_health": {
            "state": state,
            "inventory_reliable": state in {"OK", "GPU_MISSING"},
        },
        "gpus": gpus if gpus is not None else [],
    }


def _observe(
    database, device_id: int, service: GPUIncidentService, payload: dict[str, object]
) -> None:
    with database.transaction() as session:
        device = session.scalar(select(Device).where(Device.id == device_id).with_for_update())
        assert device is not None
        service.accept(session, device, payload, database_utc(session))


def test_gpu_incident_confirmation_recovery_and_offline_supersession(identity, mysql_database):
    project = identity.create_project("GPU lifecycle")
    enrolled = identity.enroll(project.public_id, "GPU device")
    service = GPUIncidentService(
        email_recipients=("ops@example.test",), sms_recipients=("+15551234567",)
    )

    _observe(mysql_database, enrolled.device.id, service, _sample("DRIVER_ERROR"))
    _observe(mysql_database, enrolled.device.id, service, _sample("NVIDIA_SMI_FAILED"))
    _observe(mysql_database, enrolled.device.id, service, _sample("DRIVER_ERROR"))

    with mysql_database.transaction() as session:
        incident = session.scalar(select(Incident).where(Incident.incident_type == "GPU"))
        assert incident is not None
        assert session.scalars(select(AlertEvent.event_kind).order_by(AlertEvent.id)).all() == [
            "GPU_DEGRADED"
        ]
        assert set(session.scalars(select(NotificationDelivery.channel)).all()) == {"EMAIL", "SMS"}
        device = session.get(Device, enrolled.device.id)
        assert device is not None
        device.monitoring_started_at = database_utc(session) - timedelta(seconds=180)

    AvailabilityService(mysql_database).sweep()

    with mysql_database.transaction() as session:
        device = session.get(Device, enrolled.device.id)
        assert device is not None
        assert device.availability_state == "OFFLINE"
        assert device.gpu_failure_streak == 0
        assert device.gpu_ok_streak == 0
        assert set(session.scalars(select(NotificationDelivery.status)).all()) == {"CANCELLED"}
        device.availability_state = "ONLINE"

    _observe(
        mysql_database,
        enrolled.device.id,
        service,
        _sample("OK", gpus=[{"uuid": "GPU-one"}]),
    )
    _observe(
        mysql_database,
        enrolled.device.id,
        service,
        _sample("OK", gpus=[{"uuid": "GPU-one"}]),
    )

    with mysql_database.transaction() as session:
        incident = session.scalar(select(Incident).where(Incident.incident_type == "GPU"))
        assert incident is not None
        assert incident.closed_at is not None
        assert session.scalars(select(AlertEvent.event_kind).order_by(AlertEvent.id)).all() == [
            "GPU_DEGRADED",
            "DEVICE_OFFLINE",
            "GPU_RECOVERED",
        ]


def test_gpu_missing_is_confirmed_from_server_expected_inventory(identity, mysql_database):
    project = identity.create_project("GPU inventory")
    enrolled = identity.enroll(project.public_id, "GPU device")
    service = GPUIncidentService()
    payload = _sample("OK", gpus=[])

    _observe(mysql_database, enrolled.device.id, service, payload)
    _observe(mysql_database, enrolled.device.id, service, payload)

    with mysql_database.transaction() as session:
        incident = session.scalar(select(Incident).where(Incident.incident_type == "GPU"))
        assert incident is not None
        assert incident.current_reason == "GPU_MISSING"
