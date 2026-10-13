"""Bounded, device-scoped incident diagnostics correlation."""

from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.dashboard.read import DashboardNotFound
from app.dashboard.service import DashboardUser
from app.main import create_app

DEVICE_ID = str(uuid4())
INCIDENT_ID = str(uuid4())
OPENED = datetime(2026, 10, 12, 12, 0)
RECOVERED = datetime(2026, 10, 12, 13, 0)


def test_correlation_resolves_open_and_recovery_windows_for_existing_incident_types(monkeypatch):
    from app.logs import correlation

    class Session:
        def execute(self, statement):
            return SimpleNamespace(
                one_or_none=lambda: (
                    SimpleNamespace(
                        incident_uuid=INCIDENT_ID,
                        incident_type=self.incident_type,
                        opened_at=OPENED,
                        closed_at=RECOVERED,
                    ),
                    SimpleNamespace(device_uuid=DEVICE_ID),
                )
            )

    class Database:
        @contextmanager
        def transaction(self):
            yield session

    calls = []

    class Logs:
        def __init__(self, database):
            pass

        def near(self, device_uuid, *, anchor, start, end, limit):
            calls.append((device_uuid, anchor, start, end, limit))
            return {"items": [{"source": "kernel", "message": "nearby"}], "truncated": False}

    monkeypatch.setattr(correlation, "LogWatchService", Logs)
    session = Session()
    service = correlation.IncidentDiagnosticService(Database())
    for incident_type in ("AVAILABILITY", "GPU"):
        session.incident_type = incident_type
        for point, anchor in (("opened", OPENED), ("recovered", RECOVERED)):
            result = service.get(DEVICE_ID, INCIDENT_ID, point=point)
            assert result["incident"]["type"] == incident_type
            assert result["incident"]["point"] == point
            assert result["diagnostics"] == [{"source": "kernel", "message": "nearby"}]
            assert calls[-1] == (
                DEVICE_ID,
                anchor,
                anchor - correlation.BEFORE_INCIDENT,
                anchor + correlation.AFTER_INCIDENT,
                50,
            )


def test_correlation_rejects_missing_incident_and_unclosed_recovery():
    from app.logs import correlation

    class Database:
        @contextmanager
        def transaction(self):
            yield SimpleNamespace(
                execute=lambda statement: SimpleNamespace(one_or_none=lambda: row)
            )

    service = correlation.IncidentDiagnosticService(Database())
    row = None
    with pytest.raises(DashboardNotFound):
        service.get(DEVICE_ID, INCIDENT_ID)
    row = (
        SimpleNamespace(
            incident_uuid=INCIDENT_ID,
            incident_type="AVAILABILITY",
            opened_at=OPENED,
            closed_at=None,
        ),
        SimpleNamespace(device_uuid=DEVICE_ID),
    )
    with pytest.raises(ValueError):
        service.get(DEVICE_ID, INCIDENT_ID, point="recovered")
    with pytest.raises(DashboardNotFound):
        service.get(str(uuid4()), INCIDENT_ID)


def test_near_query_is_bounded_to_device_window_and_stably_ordered():
    from app.logs import service as logs

    class Session:
        def scalar(self, statement):
            return 12

        def scalars(self, statement):
            compiled = str(statement.compile(dialect=mysql.dialect()))
            assert "device_log_entries.device_id" in compiled
            assert "device_log_entries.occurred_at >= " in compiled
            assert "device_log_entries.occurred_at <= " in compiled
            assert "timestampdiff(microsecond" in compiled.lower()
            assert "ORDER BY abs(timestampdiff" in compiled
            assert "device_log_entries.occurred_at, device_log_entries.id" in compiled
            assert "device_log_entries.received_at >= " not in compiled
            assert "device_log_entries.received_at <= " not in compiled
            assert " LIMIT " in compiled
            return SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(
                        id=number,
                        source="kernel",
                        occurred_at=OPENED,
                        received_at=OPENED + timedelta(minutes=20),
                        severity=None,
                        message=f"message {number}",
                    )
                    for number in range(3)
                ]
            )

    class Database:
        @contextmanager
        def transaction(self):
            yield Session()

    result = logs.LogWatchService(Database()).near(
        DEVICE_ID,
        anchor=OPENED,
        start=OPENED - logs.timedelta(minutes=5),
        end=OPENED + logs.timedelta(minutes=10),
        limit=2,
    )
    assert result["truncated"] is True
    assert [item["message"] for item in result["items"]] == ["message 0", "message 1"]
    assert all("id" not in item for item in result["items"])


def test_log_watch_incident_window_uses_occurrence_time_and_default_uses_receipt_time():
    from app.logs.service import LogWatchService

    statements = []

    class Session:
        def scalar(self, statement):
            return 12

        def scalars(self, statement):
            compiled = str(statement.compile(dialect=mysql.dialect()))
            statements.append(compiled)
            if "FROM device_log_sources" in compiled:
                return []
            return SimpleNamespace(all=lambda: [])

    class Database:
        @contextmanager
        def transaction(self):
            yield Session()

    service = LogWatchService(Database())
    for basis, expected, other in (
        ("received", "received_at", "occurred_at"),
        ("occurred", "occurred_at", "received_at"),
    ):
        service.recent(
            DEVICE_ID,
            from_time="2026-10-12T11:55:00Z",
            until="2026-10-12T12:10:00Z",
            time_basis=basis,
        )
        predicate = statements[-1].split("WHERE ", 1)[1].split(" ORDER BY ", 1)[0]
        assert f"device_log_entries.{expected} >= " in predicate
        assert f"device_log_entries.{expected} <= " in predicate
        assert f"device_log_entries.{other} >= " not in predicate
        assert f"device_log_entries.{other} <= " not in predicate
        if basis == "occurred":
            assert "device_log_entries.occurred_at IS NOT NULL" in predicate


def test_incident_diagnostics_route_requires_dashboard_session_and_keeps_errors_distinct(
    monkeypatch,
):
    from app.api import logs as api

    failure = None

    class Correlation:
        def __init__(self, database):
            pass

        def get(self, device_uuid, incident_uuid, *, point):
            assert (device_uuid, incident_uuid) == (DEVICE_ID, INCIDENT_ID)
            if failure == "database":
                raise SQLAlchemyError("unavailable")
            if point == "recovered":
                raise DashboardNotFound("Incident not found.")
            return {"incident": {"incident_id": INCIDENT_ID}, "diagnostics": []}

    class Authorized:
        def authenticate_session(self, token):
            return DashboardUser("google", "viewer@example.test", None)

    monkeypatch.setattr(api, "IncidentDiagnosticService", Correlation)
    app = create_app(
        Settings(env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test")
    )
    path = f"/api/v1/devices/{DEVICE_ID}/incidents/{INCIDENT_ID}/diagnostics"
    with TestClient(app, base_url="https://testserver") as client:
        anonymous = client.get(path)
        app.state.dashboard_auth_service = Authorized()
        client.cookies.set("__Host-skybeat_session", "valid")
        authorized = client.get(path)
        missing = client.get(f"{path}?point=recovered")
        invalid = client.get(f"{path}?point=other")
        failure = "database"
        unavailable = client.get(path)
    assert anonymous.status_code == 401
    assert authorized.status_code == 200
    assert authorized.headers["cache-control"] == "no-store"
    assert missing.status_code == 404
    assert invalid.status_code == 422
    assert unavailable.status_code == 503
    assert unavailable.headers["cache-control"] == "no-store"
