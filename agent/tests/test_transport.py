import asyncio
import time
from dataclasses import replace

import httpx
import pytest

from skybeat_agent.config import Config
from skybeat_agent.transport import HeartbeatSender


def config():
    return Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )


def snapshot():
    return {
        "schema_version": 1,
        "heartbeat_id": "de8308b2-0a52-4f80-9944-beb045f5e8e2",
        "device_id": config().device_id,
    }


def test_sender_retries_uncertain_response_with_same_snapshot():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "heartbeat_id": snapshot()["heartbeat_id"],
                "device_id": config().device_id,
                "accepted_at": "2026-09-21T10:30:00.000000Z",
            },
        )

    async def send():
        sender = HeartbeatSender(
            config(), transport=httpx.MockTransport(handler), sleep=lambda _: asyncio.sleep(0)
        )
        return await sender.send(snapshot())

    assert asyncio.run(send()) is True
    assert len(calls) == 2
    assert calls[0].content == calls[1].content
    assert b"authorization" not in calls[0].url.query


def test_sender_drops_contract_and_credential_failures_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, json={"error": {"code": "authentication_failed"}})

    async def send():
        sender = HeartbeatSender(
            config(), transport=httpx.MockTransport(handler), sleep=lambda _: asyncio.sleep(0)
        )
        return await sender.send(snapshot())

    assert asyncio.run(send()) is False
    assert len(calls) == 1


def test_sender_honors_total_snapshot_deadline_across_retries():
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.2)
        return httpx.Response(503)

    async def send():
        sender = HeartbeatSender(
            replace(config(), request_timeout=1), transport=httpx.MockTransport(handler)
        )
        started = time.monotonic()
        assert await sender.send(snapshot()) is False
        return time.monotonic() - started

    assert asyncio.run(send()) < 1.2
    assert calls


def test_sender_enters_slow_probe_mode_after_credential_failure():
    calls = []
    now = [0.0]

    def handler(request):
        calls.append(request)
        return httpx.Response(401)

    async def send():
        sender = HeartbeatSender(
            config(), transport=httpx.MockTransport(handler), clock=lambda: now[0]
        )
        assert await sender.send(snapshot()) is False
        assert await sender.send(snapshot()) is False
        now[0] = 300
        assert await sender.send(snapshot()) is False

    asyncio.run(send())
    assert len(calls) == 2


def test_sender_caps_retry_after_without_holding_the_obsolete_snapshot():
    calls = []
    now = [0.0]

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "999"})

    async def send():
        sender = HeartbeatSender(
            config(), transport=httpx.MockTransport(handler), clock=lambda: now[0]
        )
        assert await sender.send(snapshot()) is False
        assert await sender.send(snapshot()) is False
        now[0] = 300
        assert await sender.send(snapshot()) is False

    asyncio.run(send())
    assert len(calls) == 2


def test_sender_logs_safe_failure_category_without_token(caplog):
    def handler(request):
        return httpx.Response(503)

    async def send():
        sender = HeartbeatSender(
            config(),
            transport=httpx.MockTransport(handler),
            sleep=lambda _: asyncio.sleep(0),
        )
        assert await sender.send(snapshot()) is False

    asyncio.run(send())
    assert "heartbeat_send_failed" in caplog.text
    assert config().device_id in caplog.text
    assert config().token not in caplog.text
    assert "Authorization" not in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("dns unavailable"),
        httpx.ConnectError("certificate verify failed"),
        httpx.ReadTimeout("response timed out"),
    ],
    ids=["dns", "tls", "read-timeout"],
)
def test_sender_handles_network_failures_without_leaking_or_crashing(failure):
    calls = []

    def handler(request):
        calls.append(request)
        raise failure

    async def send():
        sender = HeartbeatSender(
            config(), transport=httpx.MockTransport(handler), sleep=lambda _: asyncio.sleep(0)
        )
        return await sender.send(snapshot())

    assert asyncio.run(send()) is False
    assert len(calls) == 3
