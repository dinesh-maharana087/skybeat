import json
from datetime import datetime
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

        def recent(self, requested, *, source=None, limit=60, **_filters):
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


def test_log_read_route_forwards_bounded_time_and_cursor_filters(monkeypatch):
    from app.api import logs as api

    device_id = str(uuid4())
    seen = []

    class FakeService:
        def __init__(self, database):
            pass

        def recent(self, requested, *, source, limit, from_time, until, cursor, direction):
            seen.append((requested, source, limit, from_time, until, cursor, direction))
            return {"sources": [], "items": [], "next_cursor": None}

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
        client.cookies.set("__Host-skybeat_session", "valid")
        response = client.get(
            f"/api/v1/devices/{device_id}/logs",
            params={
                "source": "kernel",
                "limit": 25,
                "from": "2026-10-01T00:00:00Z",
                "until": "2026-10-02T00:00:00Z",
                "cursor": "opaque",
                "direction": "oldest",
            },
        )
        too_large = client.get(f"/api/v1/devices/{device_id}/logs?limit=101")
        bad_direction = client.get(f"/api/v1/devices/{device_id}/logs?direction=random")
    assert response.status_code == 200
    assert too_large.status_code == bad_direction.status_code == 422
    assert seen == [
        (
            device_id,
            "kernel",
            25,
            "2026-10-01T00:00:00Z",
            "2026-10-02T00:00:00Z",
            "opaque",
            "oldest",
        )
    ]


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-10-01T00:00:00", None),
        ("bad", None),
        (None, "2026-10-01T00:00:00"),
        ("2026-10-03T00:00:00Z", "2026-10-02T00:00:00Z"),
    ],
)
def test_log_query_rejects_naive_malformed_or_reversed_utc_window(start, end):
    from app.logs import service

    with pytest.raises(ValueError):
        service.parse_log_window(start, end)


def test_log_query_normalizes_offset_time_and_binds_cursor_to_filters():
    from app.logs import service

    start, end = service.parse_log_window("2026-10-01T05:30:00+05:30", "2026-10-02T00:00:00Z")
    assert start == datetime(2026, 10, 1)
    assert end == datetime(2026, 10, 2)
    token = service.encode_log_cursor(42, "device-a", "kernel", start, end, "newest")
    assert service.decode_log_cursor(token, "device-a", "kernel", start, end, "newest") == 42
    with pytest.raises(ValueError):
        service.decode_log_cursor(token, "device-b", "kernel", start, end, "newest")
    with pytest.raises(ValueError):
        service.decode_log_cursor(token, "device-a", "system_journal", start, end, "newest")
    with pytest.raises(ValueError):
        service.decode_log_cursor(token, "device-a", "kernel", start, end, "oldest")
    with pytest.raises(ValueError):
        service.decode_log_cursor("not-base64", "device-a", "kernel", start, end, "newest")
