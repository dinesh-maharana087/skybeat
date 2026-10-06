"""Real MySQL/InnoDB Log Watch binding, deduplication, cap, and read isolation."""

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select

from app.devices.service import AuthenticationFailed
from app.logs.service import MAX_STORED_PER_SOURCE, LogWatchService
from app.models import DeviceLogEntry, DeviceLogSource
from app.schemas.logs import LogEntryUpload, LogUpload

pytestmark = pytest.mark.mysql


def _entry(number):
    return LogEntryUpload(
        entry_id=sha256(f"cursor-{number}".encode()).hexdigest(),
        occurred_at=datetime.now(UTC),
        severity="info",
        message=f"entry {number} <script>",
    )


def test_log_migration_auth_dedup_retention_and_device_isolation(identity, mysql_database):
    tables = set(inspect(mysql_database.engine).get_table_names())
    assert {"device_log_entries", "device_log_sources"} <= tables
    first = identity.enroll(identity.create_project(f"Log A {uuid4()}").public_id, "Log A")
    second = identity.enroll(identity.create_project(f"Log B {uuid4()}").public_id, "Log B")
    token = first.credential.token.get_secret_value()
    service = LogWatchService(mysql_database)
    initial = LogUpload(
        schema_version=1, source="skybeat_agent", status="available", entries=[_entry(0)]
    )
    assert service.accept(initial, token)["accepted"] == 1
    assert service.accept(initial, token)["accepted"] == 0
    with pytest.raises(AuthenticationFailed):
        service.accept(initial, second.credential.token.get_secret_value() + "bad")
    assert service.recent(second.device.device_uuid)["items"] == []
    assert service.recent(first.device.device_uuid)["items"][0]["message"] == "entry 0 <script>"
    for start in range(1, 521, 80):
        batch = [_entry(number) for number in range(start, min(start + 80, 521))]
        service.accept(
            LogUpload(schema_version=1, source="skybeat_agent", status="available", entries=batch),
            token,
        )
    with mysql_database.transaction() as session:
        count = session.scalar(
            select(func.count())
            .select_from(DeviceLogEntry)
            .where(DeviceLogEntry.device_id == first.device.id)
        )
        state = session.get(DeviceLogSource, (first.device.id, "skybeat_agent"))
    assert count == MAX_STORED_PER_SOURCE
    assert state.status == "available"
    recent = service.recent(first.device.device_uuid, source="skybeat_agent", limit=2)
    assert [item["message"] for item in recent["items"]] == [
        "entry 520 <script>",
        "entry 519 <script>",
    ]
