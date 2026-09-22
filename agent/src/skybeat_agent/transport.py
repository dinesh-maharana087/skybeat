"""HTTPS sender with bounded retries of one immutable snapshot."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from skybeat_agent.config import Config


class HeartbeatSender:
    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config
        self.transport = transport
        self.sleep = sleep

    async def send(self, snapshot: dict[str, Any]) -> bool:
        timeout = httpx.Timeout(self.config.request_timeout, connect=self.config.connect_timeout)
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            timeout=timeout, transport=self.transport, follow_redirects=False
        ) as client:
            for attempt in range(self.config.max_attempts):
                try:
                    response = await client.post(
                        f"{self.config.server_url}/api/v1/heartbeats",
                        json=snapshot,
                        headers=headers,
                    )
                except httpx.HTTPError:
                    response = None
                if response is not None and response.status_code == 200:
                    try:
                        acknowledgement = response.json()
                    except ValueError:
                        acknowledgement = {}
                    if (
                        acknowledgement.get("heartbeat_id") == snapshot["heartbeat_id"]
                        and acknowledgement.get("device_id") == snapshot["device_id"]
                    ):
                        return True
                if response is not None and response.status_code in {
                    400,
                    401,
                    403,
                    404,
                    405,
                    409,
                    413,
                    415,
                    422,
                }:
                    return False
                if attempt + 1 < self.config.max_attempts:
                    await self.sleep(min(2.0, float(attempt + 1)))
        return False
