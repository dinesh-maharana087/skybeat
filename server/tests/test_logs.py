import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dashboard.service import DashboardUser
from app.main import create_app
from app.schemas.logs import LogUploadInvalid, parse_log_upload
from app.users.service import UserRole


def upload(**overrides):
    return {
        "schema_version": 1,
        "source": "skybeat_agent",
        "status": "available",
        "entries": [
            {
                "entry_id": "a" * 64,
                "occurred_at": "2026-10-06T01:00:00Z",
                "severity": "info",
                "message": "safe <script> text",
            }
        ],
        **overrides,
    }


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "arbitrary"},
        {"source": "kernel", "device_id": str(uuid4())},
        {"entries": [{"entry_id": "a" * 64, "message": "x" * 2049}]},
        {"entries": [{"entry_id": "a" * 64, "message": "x", "occurred_at": "not-a-time"}]},
        {"entries": [{"entry_id": "a" * 64, "message": "x\x1b[31m"}]},
        {"entries": [{"entry_id": "a" * 64, "message": "x\ud800"}]},
        {"entries": [{"entry_id": "a" * 64, "message": "x"}] * 81},
        {"status": "permission_unavailable"},
    ],
)
def test_upload_schema_rejects_unsafe_or_unbounded_values(bad):
    with pytest.raises(LogUploadInvalid):
        parse_log_upload(json.dumps(upload(**bad)).encode())


def test_upload_schema_rejects_duplicate_fields_and_oversized_body():
    with pytest.raises(LogUploadInvalid):
        parse_log_upload(b'{"source":"kernel","source":"system_journal"}')
    with pytest.raises(LogUploadInvalid):
        parse_log_upload(b" " * (72 * 1024 + 1))
    assert parse_log_upload(json.dumps(upload()).encode()).source == "skybeat_agent"


def test_upload_route_rejects_anonymous_and_invalid_transport_without_database():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        anonymous = client.post("/api/v1/agent/logs", json=upload())
        invalid = client.post(
            "/api/v1/agent/logs", json=upload(), headers={"Authorization": "Bearer invalid"}
        )
        too_large = client.post(
            "/api/v1/agent/logs",
            content=b"x" * (72 * 1024 + 1),
            headers={"Content-Type": "application/json"},
        )
    assert anonymous.status_code == invalid.status_code == 401
    assert too_large.status_code == 413
    assert anonymous.headers["cache-control"] == "no-store"


def test_log_read_route_uses_current_dashboard_session_boundary():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    device_id = str(uuid4())
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        anonymous = client.get(f"/api/v1/devices/{device_id}/logs")
    assert anonymous.status_code == 401


def test_log_upload_and_read_routes_bind_to_existing_services(monkeypatch):
    from app.api import logs as api
    from app.devices.credentials import generate_credential

    device_id = str(uuid4())
    token = generate_credential().token.get_secret_value()
    seen = []

    class FakeService:
        def __init__(self, database, *, allowed=None):
            pass

        def accept(self, payload, presented_token):
            seen.append((payload.source, presented_token))
            return {"source": payload.source, "accepted": 1}

        def recent(self, requested, *, source=None, limit=60):
            seen.append((requested, source, limit))
            return {"sources": [], "items": []}

    class Authenticated:
        def authenticate_session(self, token):
            return DashboardUser("google", "viewer@example.test", None, 1, UserRole.USER)

    monkeypatch.setattr(api, "LogWatchService", FakeService)
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        accepted = client.post(
            "/api/v1/agent/logs", json=upload(), headers={"Authorization": f"Bearer {token}"}
        )
        client.cookies.set("__Host-skybeat_session", "valid")
        read = client.get(f"/api/v1/devices/{device_id}/logs?source=kernel&limit=10")
    assert accepted.status_code == 200
    assert read.status_code == 200
    assert seen == [("skybeat_agent", token), (device_id, "kernel", 10)]
