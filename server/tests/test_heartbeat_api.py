import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def sample(device_id=None, heartbeat_id=None):
    return {
        "schema_version": 1,
        "heartbeat_id": heartbeat_id or str(uuid4()),
        "device_id": device_id or str(uuid4()),
        "agent_version": "1.0.0",
        "collected_at": "2026-09-21T10:30:00Z",
        "hostname": "test-host",
        "ip_addresses": ["192.0.2.1"],
        "os": {"name": "Ubuntu", "version": "24.04", "kernel": None, "architecture": "x86_64"},
        "uptime_seconds": 0,
        "cpu": {"utilization_percent": None},
        "memory": {
            "total_bytes": None,
            "used_bytes": None,
            "available_bytes": None,
            "utilization_percent": None,
        },
        "disks": [],
        "gpu_health": {"state": "UNKNOWN", "reason_code": "disabled", "inventory_reliable": False},
        "gpus": [],
    }


@pytest.fixture
def client():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings)) as value:
        yield value


def test_missing_credential_fails_closed_without_database(client):
    response = client.post("/api/v1/heartbeats", json=sample())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "headers,body,status",
    [
        ({"content-type": "text/plain"}, b"{}", 415),
        ({"content-type": "application/json", "content-encoding": "gzip"}, b"{}", 415),
        ({"content-type": "application/json"}, b" " * 131073, 413),
    ],
    ids=["content-type", "compression", "oversize"],
)
def test_transport_envelope_rejected_before_database(client, headers, body, status):
    response = client.post("/api/v1/heartbeats", content=body, headers=headers)
    assert response.status_code == status
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_database_failure_never_acknowledges(client):
    from app.devices.credentials import generate_credential

    response = client.post(
        "/api/v1/heartbeats",
        json=sample(),
        headers={"authorization": f"Bearer {generate_credential().token.get_secret_value()}"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


def test_malformed_payload_error_does_not_echo_secrets(client):
    from app.devices.credentials import generate_credential

    token = generate_credential().token.get_secret_value()
    payload = sample()
    payload[token] = token
    response = client.post(
        "/api/v1/heartbeats",
        content=json.dumps(payload),
        headers={"content-type": "application/json", "authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert token not in response.text
