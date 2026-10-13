"""Isolated MySQL proof of bounded incident/device diagnostics matching."""

from datetime import datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest

from app.dashboard.read import DashboardNotFound
from app.logs.correlation import IncidentDiagnosticService
from app.logs.service import LogWatchService
from app.models import DeviceLogEntry, Incident

pytestmark = pytest.mark.mysql


def test_incident_diagnostics_uses_occurrence_time_despite_delayed_upload(
    identity, mysql_database
):
    first = identity.enroll(identity.create_project(f"Correlation A {uuid4()}").public_id, "A")
    second = identity.enroll(identity.create_project(f"Correlation B {uuid4()}").public_id, "B")
    anchor = datetime(2026, 10, 12, 12, 0)
    incident_uuid = str(uuid4())
    with mysql_database.transaction() as session:
        session.add(
            Incident(
                incident_uuid=incident_uuid,
                device_id=first.device.id,
                incident_type="AVAILABILITY",
                opened_at=anchor,
                detected_at=anchor,
                closed_at=None,
                close_reason=None,
                current_reason="OFFLINE",
                created_at=anchor,
                updated_at=anchor,
            )
        )
        for device, label, occurred_offset, received_offset in (
            (first, "outside-before", -6, 0),
            (first, "boundary-before", -5, 5),
            (first, "before", -1, 7),
            (first, "anchor-delayed", 0, 20),
            (first, "anchor-second", 0, 21),
            (first, "after", 1, 1),
            (first, "boundary-after", 10, 10),
            (first, "outside-after", 11, 0),
            (first, "missing-occurrence", None, 0),
            (second, "wrong-device", 0, 0),
        ):
            message = f"{device.device.device_uuid} {label}"
            session.add(
                DeviceLogEntry(
                    device_id=device.device.id,
                    source="kernel",
                    entry_hash=sha256(message.encode()).digest(),
                    occurred_at=(
                        anchor + timedelta(minutes=occurred_offset)
                        if occurred_offset is not None
                        else None
                    ),
                    received_at=anchor + timedelta(minutes=received_offset),
                    severity="info",
                    message=message,
                )
            )
    service = IncidentDiagnosticService(mysql_database)
    result = service.get(first.device.device_uuid, incident_uuid)
    messages = [item["message"] for item in result["diagnostics"]]
    assert messages == [
        f"{first.device.device_uuid} anchor-delayed",
        f"{first.device.device_uuid} anchor-second",
        f"{first.device.device_uuid} before",
        f"{first.device.device_uuid} after",
        f"{first.device.device_uuid} boundary-before",
        f"{first.device.device_uuid} boundary-after",
    ]
    assert result["diagnostics"][0]["occurred_at"] == "2026-10-12T12:00:00Z"
    assert result["diagnostics"][0]["received_at"] == "2026-10-12T12:20:00Z"
    assert result["truncated"] is False
    assert all("id" not in item and "entry_hash" not in item for item in result["diagnostics"])
    logs = LogWatchService(mysql_database)
    watch_messages = []
    cursor = None
    while True:
        page = logs.recent(
            first.device.device_uuid,
            source="kernel",
            from_time=result["window_start"],
            until=result["window_end"],
            time_basis="occurred",
            limit=2,
            cursor=cursor,
        )
        watch_messages.extend(item["message"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert set(watch_messages) == set(messages)
    assert len(watch_messages) == len(messages)
    ordinary = logs.recent(
        first.device.device_uuid,
        source="kernel",
        from_time=result["window_start"],
        until=result["window_end"],
    )
    assert f"{first.device.device_uuid} anchor-delayed" not in {
        item["message"] for item in ordinary["items"]
    }
    nearby = LogWatchService(mysql_database).near(
        first.device.device_uuid,
        anchor=anchor,
        start=anchor - timedelta(minutes=5),
        end=anchor + timedelta(minutes=10),
        limit=2,
    )
    assert len(nearby["items"]) == 2
    assert nearby["truncated"] is True
    with pytest.raises(DashboardNotFound):
        service.get(second.device.device_uuid, incident_uuid)
