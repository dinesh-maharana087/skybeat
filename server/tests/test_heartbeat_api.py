import asyncio
import json
import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.schemas.heartbeat import MAX_BODY_BYTES


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


def test_chunked_oversize_is_rejected_without_consuming_following_body_chunk():
    """An ASGI body over the cap must not be accumulated through request.body()."""
    from app.devices.credentials import generate_credential

    app = create_app(
        Settings(env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test")
    )
    token = generate_credential().token.get_secret_value()
    chunks = [(b"x" * (MAX_BODY_BYTES + 1), True), (b"must-not-be-read", False)]
    received = 0
    sent = []

    async def receive():
        nonlocal received
        body, more_body = chunks[received]
        received += 1
        return {"type": "http.request", "body": body, "more_body": more_body}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/v1/heartbeats",
        "raw_path": b"/api/v1/heartbeats",
        "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"authorization", f"Bearer {token}".encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }

    asyncio.run(app(scope, receive, send))

    assert received == 1
    assert (
        next(message for message in sent if message["type"] == "http.response.start")["status"]
        == 413
    )


def test_database_failure_never_acknowledges(client):
    from app.devices.credentials import generate_credential

    response = client.post(
        "/api/v1/heartbeats",
        json=sample(),
        headers={"authorization": f"Bearer {generate_credential().token.get_secret_value()}"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"


def test_synchronous_heartbeat_storage_does_not_block_other_requests(monkeypatch):
    from app.devices.credentials import generate_credential
    from app.heartbeats.service import AcceptedHeartbeat, HeartbeatService

    def slow_accept(self, heartbeat, token):
        time.sleep(0.15)
        return AcceptedHeartbeat(
            {
                "schema_version": 1,
                "heartbeat_id": heartbeat.heartbeat_id,
                "device_id": heartbeat.device_id,
                "accepted_at": "2026-09-21T10:30:00.000000Z",
            }
        )

    monkeypatch.setattr(HeartbeatService, "accept", slow_accept)
    app = create_app(
        Settings(env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test")
    )
    token = generate_credential().token.get_secret_value()

    async def send_all():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            started = time.monotonic()
            responses = await asyncio.gather(
                client.post(
                    "/api/v1/heartbeats",
                    json=sample(),
                    headers={"authorization": f"Bearer {token}"},
                ),
                client.post(
                    "/api/v1/heartbeats",
                    json=sample(),
                    headers={"authorization": f"Bearer {token}"},
                ),
            )
        return responses, time.monotonic() - started

    responses, elapsed = asyncio.run(send_all())
    assert [response.status_code for response in responses] == [200, 200]
    assert elapsed < 0.25


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
