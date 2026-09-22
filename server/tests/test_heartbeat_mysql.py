import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import OperationalError
from test_heartbeat_api import sample

from app.devices.service import IdentityService
from app.main import create_app
from app.models import Device

pytestmark = pytest.mark.mysql


@pytest.fixture
def endpoint(mysql_database, mysql_settings):
    identity = IdentityService(mysql_database, actor="heartbeat-test")
    project = identity.create_project("Heartbeat test")
    enrolled = identity.enroll(project.public_id, "Telemetry device")
    with TestClient(create_app(mysql_settings, database=mysql_database)) as client:
        yield client, identity, enrolled


def send(endpoint, payload=None, token=None):
    client, _, enrolled = endpoint
    token = token or enrolled.credential.token.get_secret_value()
    return client.post(
        "/api/v1/heartbeats",
        json=payload or sample(enrolled.device.device_uuid),
        headers={"authorization": f"Bearer {token}"},
    )


def test_acceptance_persists_all_rows_and_original_ack(endpoint, mysql_database):
    response = send(endpoint)
    assert response.status_code == 200
    from app.models.heartbeat import DeviceLatest, HeartbeatReceipt, HeartbeatSample

    device_id = endpoint[2].device.id
    with mysql_database.transaction() as session:
        latest = session.get(DeviceLatest, device_id)
        assert latest.payload["hostname"] == "test-host"
        assert latest.payload["cpu"]["utilization_percent"] is None
        assert latest.payload["uptime_seconds"] == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(HeartbeatSample)
                .where(HeartbeatSample.device_id == device_id)
            )
            == 1
        )
        receipt = session.scalar(
            select(HeartbeatReceipt).where(HeartbeatReceipt.device_id == device_id)
        )
        assert receipt.response_payload == response.json()
        assert (receipt.expires_at - receipt.received_at).total_seconds() >= 86400
        assert session.get(Device, device_id).last_seen_at == receipt.received_at
        assert receipt.received_at != latest.collected_at


def test_identical_retry_keeps_latest_and_liveness_after_newer_snapshot(endpoint, mysql_database):
    payload = sample(endpoint[2].device.device_uuid)
    original = send(endpoint, payload)
    assert original.status_code == 200
    newer = sample(endpoint[2].device.device_uuid)
    newer["hostname"] = "new-host"
    newer_response = send(endpoint, newer)
    retry = endpoint[0].post(
        "/api/v1/heartbeats",
        content=json.dumps(payload, indent=4, sort_keys=True),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {endpoint[2].credential.token.get_secret_value()}",
        },
    )
    assert retry.json() == original.json()
    from app.models.heartbeat import DeviceLatest, HeartbeatSample

    with mysql_database.transaction() as session:
        latest = session.get(DeviceLatest, endpoint[2].device.id)
        assert latest.payload["hostname"] == "new-host"
        assert latest.heartbeat_id == newer_response.json()["heartbeat_id"]
        assert session.get(Device, latest.device_id).last_seen_at == latest.received_at
        assert (
            session.scalar(
                select(func.count())
                .select_from(HeartbeatSample)
                .where(HeartbeatSample.device_id == latest.device_id)
            )
            == 2
        )


def test_conflict_and_revoked_retry_do_not_change_state(endpoint, mysql_database):
    payload = sample(endpoint[2].device.device_uuid)
    accepted = send(endpoint, payload)
    assert accepted.status_code == 200
    payload["hostname"] = "changed"
    conflict = send(endpoint, payload)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "heartbeat_id_conflict"
    endpoint[1].revoke(endpoint[2].device.device_uuid, endpoint[2].credential.credential_id)
    assert send(endpoint, payload).status_code == 401


def test_concurrent_duplicate_is_serialized_once(endpoint, mysql_database):
    payload = sample(endpoint[2].device.device_uuid)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: send(endpoint, payload), range(4)))
    assert [r.status_code for r in responses] == [200] * 4
    assert all(r.json() == responses[0].json() for r in responses)
    from app.models.heartbeat import HeartbeatSample

    with mysql_database.transaction() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(HeartbeatSample)
                .where(HeartbeatSample.device_id == endpoint[2].device.id)
            )
            == 1
        )


def test_identity_mismatch_and_disabled_device_rejected(endpoint):
    assert send(endpoint, sample()).status_code == 403
    endpoint[1].set_enabled(endpoint[2].device.device_uuid, False)
    assert send(endpoint).status_code in {401, 403}


def test_failed_commit_rolls_back_receipt_sample_latest_and_liveness(endpoint, mysql_database):
    def fail_commit(connection):
        raise OperationalError("commit", {}, Exception("sensitive-detail"))

    event.listen(mysql_database.engine, "commit", fail_commit)
    try:
        response = send(endpoint)
        assert response.status_code == 503
        assert "sensitive-detail" not in response.text
    finally:
        event.remove(mysql_database.engine, "commit", fail_commit)
    from app.models.heartbeat import DeviceLatest, HeartbeatReceipt, HeartbeatSample

    with mysql_database.transaction() as session:
        assert session.get(Device, endpoint[2].device.id).last_seen_at is None
        assert session.get(DeviceLatest, endpoint[2].device.id) is None
        for table in (HeartbeatReceipt, HeartbeatSample):
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(table)
                    .where(table.device_id == endpoint[2].device.id)
                )
                == 0
            )
    assert send(endpoint).status_code == 200


def test_row_lock_timeout_returns_temporary_failure(endpoint, mysql_database):
    with mysql_database.transaction() as session:
        session.execute(select(Device).where(Device.id == endpoint[2].device.id).with_for_update())
        assert send(endpoint).status_code == 503
    assert send(endpoint).status_code == 200


def test_rate_limit_shared_across_credentials_does_not_refresh_presence(endpoint, mysql_database):
    payload = sample(endpoint[2].device.device_uuid)
    first = send(endpoint, payload)
    assert first.status_code == 200
    rotated = endpoint[1].rotate(endpoint[2].device.device_uuid)
    for _ in range(5):
        assert send(endpoint, payload, rotated.token.get_secret_value()).status_code == 200
    rejected = send(endpoint)
    assert rejected.status_code == 429
    assert 1 <= int(rejected.headers["retry-after"]) <= 10
    with mysql_database.transaction() as session:
        last_seen = session.execute(
            text("SELECT last_seen_at FROM devices WHERE id=:id"), {"id": endpoint[2].device.id}
        ).scalar_one()
        assert last_seen.isoformat(timespec="microseconds") + "Z" == first.json()["accepted_at"]
