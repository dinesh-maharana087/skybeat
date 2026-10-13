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


def test_log_upload_and_read_routes_bind_to_existing_services(monkeypatch, capfd):
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
            return {"source": payload.source, "accepted": 1, "duplicates": 2}

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
    assert accepted.json()["duplicates"] == 2
    assert read.status_code == 200
    assert seen == [("skybeat_agent", token), (device_id, "kernel", 10)]
    logged = capfd.readouterr().err
    assert "log_upload_accepted" in logged
    assert "accepted=1 duplicates=2" in logged
    assert token not in logged


def test_diagnostics_rate_limit_is_separate_from_heartbeat_limit():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    assert all(app.state.log_limiter.allow(1) for _ in range(6))
    assert app.state.log_limiter.allow(1) is False
    assert app.state.log_limiter.allow(2) is True
    assert app.state.heartbeat_limiter.allow(1) is True


@pytest.mark.parametrize("failure,status", [("storage", 503), ("rate_limit", 429)])
def test_log_failure_does_not_change_heartbeat_result(monkeypatch, failure, status):
    from sqlalchemy.exc import SQLAlchemyError

    from app.devices.credentials import generate_credential
    from app.heartbeats.service import AcceptedHeartbeat, HeartbeatService
    from app.logs.service import LogRateLimited, LogWatchService
    from tests.heartbeat_fixtures import heartbeat_payload

    def failed_log(self, upload, token):
        if failure == "rate_limit":
            raise LogRateLimited()
        raise SQLAlchemyError("diagnostics unavailable")

    def accepted_heartbeat(self, heartbeat, token):
        return AcceptedHeartbeat(
            {
                "schema_version": 1,
                "heartbeat_id": heartbeat.heartbeat_id,
                "device_id": heartbeat.device_id,
                "accepted_at": "2026-10-09T00:00:00.000000Z",
            }
        )

    monkeypatch.setattr(LogWatchService, "accept", failed_log)
    monkeypatch.setattr(HeartbeatService, "accept", accepted_heartbeat)
    app = create_app(
        Settings(env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test")
    )
    token = generate_credential().token.get_secret_value()
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app, base_url="https://testserver") as client:
        diagnostic = client.post("/api/v1/agent/logs", json=upload(), headers=headers)
        heartbeat = client.post("/api/v1/heartbeats", json=heartbeat_payload(), headers=headers)
    assert diagnostic.status_code == status
    if status == 429:
        assert diagnostic.headers["retry-after"] == "60"
    assert heartbeat.status_code == 200
    assert heartbeat.json()["heartbeat_id"] == heartbeat_payload()["heartbeat_id"]


def test_log_read_route_forwards_bounded_time_and_cursor_filters(monkeypatch):
    from app.api import logs as api

    device_id = str(uuid4())
    seen = []

    class FakeService:
        def __init__(self, database):
            pass

        def recent(
            self, requested, *, source, limit, from_time, until, cursor, direction, q, time_basis
        ):
            seen.append((requested, source, limit, from_time, until, cursor, direction, q, time_basis))
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
                "q": "  GPU  error ",
            },
        )
        too_large = client.get(f"/api/v1/devices/{device_id}/logs?limit=101")
        too_long_search = client.get(f"/api/v1/devices/{device_id}/logs?q={'x' * 129}")
        bad_direction = client.get(f"/api/v1/devices/{device_id}/logs?direction=random")
        occurred = client.get(f"/api/v1/devices/{device_id}/logs?time_basis=occurred")
        bad_basis = client.get(f"/api/v1/devices/{device_id}/logs?time_basis=unknown")
    assert response.status_code == 200
    assert occurred.status_code == 200
    assert (
        too_large.status_code
        == too_long_search.status_code
        == bad_direction.status_code
        == bad_basis.status_code
        == 422
    )
    assert seen == [
        (
            device_id,
            "kernel",
            25,
            "2026-10-01T00:00:00Z",
            "2026-10-02T00:00:00Z",
            "opaque",
            "oldest",
            "  GPU  error ",
            "received",
        ),
        (device_id, None, 60, None, None, None, "newest", None, "occurred"),
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


def test_log_search_normalizes_plain_text_and_escapes_like_characters():
    from app.logs.service import log_search_pattern, normalize_log_search

    assert normalize_log_search("  GPU   error  ") == "GPU error"
    assert normalize_log_search("  ") is None
    assert log_search_pattern(r"50%_ / \\ '雪") == r"%50/%/_ // \\ '雪%"
    with pytest.raises(ValueError):
        normalize_log_search("x" * 129)
    with pytest.raises(ValueError):
        normalize_log_search("GPU\nerror")


def test_search_cursor_is_bound_to_normalized_query_and_old_cursor_remains_compatible():
    from app.logs import service

    searched = service.encode_log_cursor(42, "device-a", None, None, None, "newest", "GPU error")
    assert (
        service.decode_log_cursor(searched, "device-a", None, None, None, "newest", "GPU error")
        == 42
    )
    with pytest.raises(ValueError):
        service.decode_log_cursor(searched, "device-a", None, None, None, "newest", "other")
    with pytest.raises(ValueError):
        service.decode_log_cursor(searched, "device-a", None, None, None, "newest")
    old = service.encode_log_cursor(43, "device-a", None, None, None, "newest")
    assert service.decode_log_cursor(old, "device-a", None, None, None, "newest") == 43
    unicode_query = "雪" * 128
    unicode_cursor = service.encode_log_cursor(
        44, "device-a", None, None, None, "newest", unicode_query
    )
    assert len(unicode_cursor) <= 2048
    assert (
        service.decode_log_cursor(
            unicode_cursor, "device-a", None, None, None, "newest", unicode_query
        )
        == 44
    )
    emoji_query = "😀" * 128
    emoji_cursor = service.encode_log_cursor(
        45, "device-a", None, None, None, "newest", emoji_query
    )
    assert len(emoji_cursor) <= 2048
    assert (
        service.decode_log_cursor(emoji_cursor, "device-a", None, None, None, "newest", emoji_query)
        == 45
    )


def test_occurrence_cursor_is_bound_to_time_basis_and_existing_cursors_remain_valid():
    from app.logs import service

    start = datetime(2026, 10, 12, 11, 55)
    end = datetime(2026, 10, 12, 12, 10)
    occurred = service.encode_log_cursor(
        42, "device-a", "kernel", start, end, "newest", "GPU", "occurred"
    )
    assert (
        service.decode_log_cursor(
            occurred, "device-a", "kernel", start, end, "newest", "GPU", "occurred"
        )
        == 42
    )
    with pytest.raises(ValueError):
        service.decode_log_cursor(occurred, "device-a", "kernel", start, end, "newest", "GPU")
    with pytest.raises(ValueError):
        service.decode_log_cursor(
            occurred, "device-a", "kernel", start, end, "newest", "other", "occurred"
        )
    received = service.encode_log_cursor(43, "device-a", "kernel", start, end, "newest", "GPU")
    assert (
        service.decode_log_cursor(received, "device-a", "kernel", start, end, "newest", "GPU")
        == 43
    )
    with pytest.raises(ValueError):
        service.decode_log_cursor(
            received, "device-a", "kernel", start, end, "newest", "GPU", "occurred"
        )
