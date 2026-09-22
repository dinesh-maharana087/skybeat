import asyncio

import httpx

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
