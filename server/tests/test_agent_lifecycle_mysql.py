"""One-slot lifecycle and device credential isolation on dedicated MySQL only."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_heartbeat_api import sample

from app.devices.service import IdentityService, NotFound
from app.lifecycle.service import AgentLifecycleService, LifecycleConflict
from app.main import create_app

pytestmark = pytest.mark.mysql


def test_one_device_operation_is_pinned_and_isolated(mysql_database, mysql_settings, tmp_path):
    identity = IdentityService(mysql_database, actor="lifecycle-test")
    project = identity.create_project("Lifecycle test")
    first = identity.enroll(project.public_id, "Lifecycle first")
    second = identity.enroll(project.public_id, "Lifecycle second")
    with TestClient(create_app(mysql_settings, database=mysql_database)) as client:
        for enrolled in (first, second):
            payload = sample(enrolled.device.device_uuid)
            payload["agent_version"] = "1.0.4"
            response = client.post(
                "/api/v1/heartbeats",
                json=payload,
                headers={"Authorization": f"Bearer {enrolled.credential.token.get_secret_value()}"},
            )
            assert response.status_code == 200

    archive = tmp_path / "approved.zip"
    archive.write_bytes(b"approved immutable release fixture")

    class ApprovedRelease:
        def current(self):
            return SimpleNamespace(version="1.0.5", wheel_sha256="a" * 64)

        def archive(self):
            return archive

    service = AgentLifecycleService(mysql_database, ApprovedRelease())
    first_token = first.credential.token.get_secret_value()
    second_token = second.credential.token.get_secret_value()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: service.request_upgrade(first.device.device_uuid, "owner@example.test"),
                range(2),
            )
        )
    assert results[0] == results[1]
    requested = results[0]
    operation_id = requested["operation"]["operation_id"]
    assert service.request_upgrade(first.device.device_uuid, "owner@example.test") == requested
    assert service.device_operation(first_token)["operation"]["operation_id"] == operation_id
    assert service.device_operation(second_token) == {"operation": None}
    assert service.device_archive(first_token, operation_id) == archive
    with pytest.raises(NotFound):
        service.device_archive(second_token, operation_id)
    archive.write_bytes(b"replacement archive")
    with pytest.raises(ValueError):
        service.device_archive(first_token, operation_id)
    succeeded = service.device_report(
        first_token,
        operation_id,
        "SUCCEEDED",
        previous_wheel_sha256="b" * 64,
        rollback_available=True,
    )
    assert succeeded["operation"]["state"] == "SUCCEEDED"
    assert (
        service.device_report(
            first_token,
            operation_id,
            "SUCCEEDED",
            previous_wheel_sha256="b" * 64,
            rollback_available=True,
        )
        == succeeded
    )
    with pytest.raises(NotFound):
        service.device_report(
            second_token, operation_id, "FAILED", failure_category="verification_failed"
        )
    with pytest.raises(LifecycleConflict):
        service.request_rollback(first.device.device_uuid, "owner@example.test")
    with TestClient(create_app(mysql_settings, database=mysql_database)) as client:
        heartbeat = sample(first.device.device_uuid)
        heartbeat["agent_version"] = "1.0.5"
        assert (
            client.post(
                "/api/v1/heartbeats",
                json=heartbeat,
                headers={"Authorization": f"Bearer {first_token}"},
            ).status_code
            == 200
        )
    rollback = service.request_rollback(first.device.device_uuid, "owner@example.test")
    assert rollback["operation"]["action"] == "ROLLBACK"
    assert rollback["operation"]["target_version"] == "1.0.4"
    assert rollback["operation"]["target_wheel_sha256"] == "b" * 64
