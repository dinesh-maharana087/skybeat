"""Fixed lifecycle API boundaries without an external database."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dashboard.service import DashboardUser
from app.devices.credentials import generate_credential
from app.main import create_app
from app.users.service import UserRole


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.ADMIN, UserRole.USER])
def test_only_management_roles_can_request_a_device_upgrade(monkeypatch, role):
    from app.api import lifecycle as api

    device_id = str(uuid4())
    calls = []

    class FakeService:
        def request_upgrade(self, requested, actor):
            calls.append((requested, actor))
            return {"operation": {"state": "REQUESTED"}}

    class Authorized:
        def authenticate_session(self, token):
            return DashboardUser("google", "operator@example.test", None, 1, role)

    monkeypatch.setattr(api, "_service", lambda request: FakeService())
    app = create_app(
        Settings(env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test")
    )
    app.state.dashboard_auth_service = Authorized()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid")
        response = client.post(f"/api/v1/devices/{device_id}/agent-lifecycle/upgrade")
        rejected = client.post(
            f"/api/v1/devices/{device_id}/agent-lifecycle/upgrade",
            json={"command": "systemctl restart"},
        )
    assert response.status_code == (403 if role == UserRole.USER else 202)
    assert rejected.status_code == (403 if role == UserRole.USER else 422)
    assert calls == ([] if role == UserRole.USER else [(device_id, "operator@example.test")])


def test_device_endpoints_use_only_its_credential_and_report_a_fixed_state(monkeypatch):
    from app.api import lifecycle as api

    token = generate_credential().token.get_secret_value()
    calls = []

    class FakeService:
        def device_operation(self, supplied):
            calls.append(("poll", supplied))
            return {"operation": None}

        def device_report(self, supplied, operation_id, state, **fields):
            calls.append(("report", supplied, operation_id, state, fields))
            return {"operation": {"state": state}}

    monkeypatch.setattr(api, "_service", lambda request: FakeService())
    app = create_app(
        Settings(env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test")
    )
    with TestClient(app, base_url="https://testserver") as client:
        unauthenticated = client.get("/api/v1/agent-lifecycle/operation")
        polling = client.get(
            "/api/v1/agent-lifecycle/operation", headers={"Authorization": f"Bearer {token}"}
        )
        report = client.post(
            "/api/v1/agent-lifecycle/report",
            headers={"Authorization": f"Bearer {token}"},
            json={"operation_id": str(uuid4()), "state": "VERIFYING"},
        )
        invalid = client.post(
            "/api/v1/agent-lifecycle/report",
            headers={"Authorization": f"Bearer {token}"},
            json={"operation_id": str(uuid4()), "state": "VERIFYING", "command": "sh"},
        )
        raw_failure = client.post(
            "/api/v1/agent-lifecycle/report",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "operation_id": str(uuid4()),
                "state": "FAILED",
                "failure_category": "verification_failed",
                "failure_detail": "raw exception includes a token",
            },
        )
    assert unauthenticated.status_code == 401
    assert polling.status_code == report.status_code == 200
    assert invalid.status_code == 422
    assert raw_failure.status_code == 422
    assert [call[0] for call in calls] == ["poll", "report"]
    assert all(call[1] == token for call in calls)


def test_version_compatibility_is_agent_api_based_not_server_version():
    from app.lifecycle.service import FIRST_CAPABLE_VERSION, _version

    assert FIRST_CAPABLE_VERSION == (1, 0, 4)
    assert _version("1.0.3") < FIRST_CAPABLE_VERSION
    assert _version("1.0.4") == FIRST_CAPABLE_VERSION
    assert _version("unknown") is None


@pytest.mark.parametrize(
    ("reported", "approved", "operation", "compatibility", "upgrade", "rollback"),
    [
        (None, "1.0.5", None, "UNKNOWN", False, False),
        ("1.0.0", "1.0.5", None, "BOOTSTRAP_REQUIRED", False, False),
        ("1.0.4", "1.0.5", None, "UPGRADE_AVAILABLE", True, False),
        ("1.0.4", None, None, "RELEASE_UNAVAILABLE", False, False),
        ("1.0.5", "1.0.5", None, "CURRENT", False, False),
        ("1.0.5", "1.0.5", ("SUCCEEDED", "1.0.5", True), "CURRENT", False, True),
        ("1.0.4", "1.0.5", ("SUCCEEDED", "1.0.5", True), "UPGRADE_AVAILABLE", False, False),
        ("1.0.4", "1.0.5", ("REQUESTED", "1.0.5", False), "IN_PROGRESS", False, False),
    ],
)
def test_overview_exposes_server_action_eligibility(
    reported, approved, operation, compatibility, upgrade, rollback
):
    from app.lifecycle.service import AgentLifecycleService
    from app.models import DeviceAgentLifecycle, DeviceLatest
    from app.releases.service import ReleaseUnavailable

    device_id = str(uuid4())
    device = SimpleNamespace(id=1, device_uuid=device_id)
    latest = SimpleNamespace(agent_version=reported) if reported is not None else None
    row = None
    if operation is not None:
        state, target, available = operation
        now = datetime.now(UTC)
        row = SimpleNamespace(
            operation_uuid=str(uuid4()),
            action="UPGRADE",
            state=state,
            target_version=target,
            target_wheel_sha256="a" * 64,
            archive_sha256="b" * 64,
            previous_version="1.0.4",
            previous_wheel_sha256="c" * 64,
            rollback_available=available,
            failure_category=None,
            failure_detail=None,
            requested_at=now,
            updated_at=now,
            completed_at=now,
        )

    class Session:
        def scalar(self, _query):
            return device

        def get(self, model, _id):
            return {DeviceLatest: latest, DeviceAgentLifecycle: row}[model]

    class Database:
        def transaction(self):
            from contextlib import nullcontext

            return nullcontext(Session())

    class Releases:
        def current(self):
            if approved is None:
                raise ReleaseUnavailable("unavailable")
            return SimpleNamespace(version=approved)

    result = AgentLifecycleService(Database(), Releases()).overview(device_id)
    assert result["compatibility"] == compatibility
    assert result["installed_version"] == reported
    assert result["actions"] == {"upgrade": upgrade, "rollback": rollback}


def test_failure_detail_is_bound_to_a_fixed_category_before_database_access():
    from app.lifecycle.service import AgentLifecycleService

    service = AgentLifecycleService(None, None)
    with pytest.raises(ValueError, match="does not match"):
        service.device_report(
            "unused",
            str(uuid4()),
            "FAILED",
            failure_category="rollback_failed",
            failure_detail="archive_digest_mismatch",
        )
