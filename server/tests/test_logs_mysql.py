"""Real MySQL/InnoDB Log Watch binding, deduplication, cap, and read isolation."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select, update

from app.devices.service import AuthenticationFailed
from app.logs.service import MAX_STORED_PER_SOURCE, LogRetentionService, LogWatchService
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
    inspector = inspect(mysql_database.engine)
    tables = set(inspector.get_table_names())
    assert {"device_log_entries", "device_log_sources"} <= tables
    assert "ix_device_log_entries_retention" in {
        index["name"] for index in inspector.get_indexes("device_log_entries")
    }
    assert "ix_device_log_sources_retention" in {
        index["name"] for index in inspector.get_indexes("device_log_sources")
    }
    assert all(
        fk["options"].get("ondelete") == "RESTRICT"
        for table in ("device_log_entries", "device_log_sources")
        for fk in inspector.get_foreign_keys(table)
    )
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


def test_log_query_uses_server_utc_window_and_stable_device_scoped_cursor(identity, mysql_database):
    first = identity.enroll(identity.create_project(f"Query A {uuid4()}").public_id, "Query A")
    second = identity.enroll(identity.create_project(f"Query B {uuid4()}").public_id, "Query B")
    service = LogWatchService(mysql_database)
    token = first.credential.token.get_secret_value()
    for source, numbers in (("kernel", (1, 2, 3, 4)), ("system_journal", (5,))):
        service.accept(
            LogUpload(
                schema_version=1,
                source=source,
                status="available",
                entries=[_entry(number) for number in numbers],
            ),
            token,
        )
    with mysql_database.transaction() as session:
        ids = session.scalars(
            select(DeviceLogEntry.id)
            .where(DeviceLogEntry.device_id == first.device.id)
            .order_by(DeviceLogEntry.id)
        ).all()
        session.execute(
            update(DeviceLogEntry)
            .where(DeviceLogEntry.id.in_(ids[:2]))
            .values(received_at=datetime(2026, 10, 1))
        )
        session.execute(
            update(DeviceLogEntry)
            .where(DeviceLogEntry.id.in_(ids[2:]))
            .values(received_at=datetime(2026, 10, 2))
        )
    first_page = service.recent(first.device.device_uuid, source="kernel", limit=2)
    second_page = service.recent(
        first.device.device_uuid,
        source="kernel",
        limit=2,
        cursor=first_page["next_cursor"],
    )
    assert [item["message"] for item in first_page["items"]] == [
        "entry 4 <script>",
        "entry 3 <script>",
    ]
    assert [item["message"] for item in second_page["items"]] == [
        "entry 2 <script>",
        "entry 1 <script>",
    ]
    assert second_page["next_cursor"] is None
    window = service.recent(
        first.device.device_uuid,
        source="kernel",
        from_time="2026-10-02T05:30:00+05:30",
        until="2026-10-02T23:59:59Z",
        direction="oldest",
    )
    assert [item["message"] for item in window["items"]] == [
        "entry 3 <script>",
        "entry 4 <script>",
    ]
    assert service.recent(second.device.device_uuid)["items"] == []
    with pytest.raises(ValueError):
        service.recent(
            first.device.device_uuid,
            source="system_journal",
            cursor=first_page["next_cursor"],
        )


def test_log_retention_prunes_old_rows_in_bounded_batches_without_cross_device_loss(
    identity, mysql_database
):
    first = identity.enroll(identity.create_project(f"Retention A {uuid4()}").public_id, "A")
    second = identity.enroll(identity.create_project(f"Retention B {uuid4()}").public_id, "B")
    service = LogWatchService(mysql_database)
    for enrolled, source, number in (
        (first, "kernel", 1),
        (first, "system_journal", 2),
        (second, "kernel", 3),
    ):
        service.accept(
            LogUpload(
                schema_version=1, source=source, status="available", entries=[_entry(number)]
            ),
            enrolled.credential.token.get_secret_value(),
        )
    with mysql_database.transaction() as session:
        old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8)
        session.execute(
            update(DeviceLogEntry)
            .where(DeviceLogEntry.device_id == first.device.id, DeviceLogEntry.source == "kernel")
            .values(received_at=old)
        )
        session.execute(
            update(DeviceLogSource)
            .where(DeviceLogSource.device_id == first.device.id, DeviceLogSource.source == "kernel")
            .values(checked_at=old)
        )
    assert LogRetentionService(mysql_database).prune_expired(retention_days=7) == (1, 1)
    assert service.recent(first.device.device_uuid, source="kernel")["items"] == []
    assert service.recent(first.device.device_uuid)["sources"][2]["status"] == "no_report"
    assert [item["message"] for item in service.recent(first.device.device_uuid)["items"]] == [
        "entry 2 <script>"
    ]
    assert [item["message"] for item in service.recent(second.device.device_uuid)["items"]] == [
        "entry 3 <script>"
    ]


def test_log_retention_revisits_backlog_in_fixed_batches(identity, mysql_database, monkeypatch):
    import app.logs.service as log_service

    enrolled = identity.enroll(identity.create_project(f"Retention batch {uuid4()}").public_id, "B")
    token = enrolled.credential.token.get_secret_value()
    service = LogWatchService(mysql_database)
    service.accept(
        LogUpload(
            schema_version=1,
            source="kernel",
            status="available",
            entries=[_entry(number) for number in (11, 12, 13)],
        ),
        token,
    )
    with mysql_database.transaction() as session:
        session.execute(
            update(DeviceLogEntry)
            .where(DeviceLogEntry.device_id == enrolled.device.id)
            .values(received_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8))
        )
    monkeypatch.setattr(log_service, "RETENTION_BATCH_SIZE", 2)
    retention = LogRetentionService(mysql_database)
    assert retention.prune_expired(retention_days=7)[0] == 2
    assert len(service.recent(enrolled.device.device_uuid)["items"]) == 1
    assert retention.prune_expired(retention_days=7)[0] == 1
    assert service.recent(enrolled.device.device_uuid)["items"] == []
