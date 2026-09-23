"""HTTPS sender with bounded retries of one immutable snapshot."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

import httpx

from skybeat_agent.config import Config

logger = logging.getLogger(__name__)


class HeartbeatSender:
    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.config = config
        self.transport = transport
        self.sleep = sleep
        self.clock = clock
        self._next_send_at = 0.0
        self._outage_delay = 0.0
        self._last_failure: str | None = None

    async def send(self, snapshot: dict[str, Any]) -> bool:
        now = self.clock()
        if now < self._next_send_at:
            return False
        deadline = now + self.config.request_timeout
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(transport=self.transport, follow_redirects=False) as client:
            for attempt in range(self.config.max_attempts):
                remaining = deadline - self.clock()
                if remaining <= 0:
                    break
                timeout = httpx.Timeout(
                    remaining, connect=min(self.config.connect_timeout, remaining)
                )
                try:
                    response = await asyncio.wait_for(
                        client.post(
                            f"{self.config.server_url}/api/v1/heartbeats",
                            json=snapshot,
                            headers=headers,
                            timeout=timeout,
                        ),
                        timeout=remaining,
                    )
                except (TimeoutError, httpx.HTTPError):
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
                        self._outage_delay = 0.0
                        self._next_send_at = 0.0
                        if self._last_failure is not None:
                            logger.info(
                                "heartbeat_send_recovered device_id=%s",
                                self.config.device_id,
                            )
                            self._last_failure = None
                        return True
                if response is not None and response.status_code in {401, 403}:
                    self._log_failure("credential_or_policy")
                    self._next_send_at = self.clock() + 300
                    return False
                if response is not None and response.status_code == 429:
                    self._log_failure("rate_limited")
                    self._next_send_at = self.clock() + self._retry_after(response)
                    return False
                if response is not None and response.status_code in {
                    400,
                    404,
                    405,
                    409,
                    413,
                    415,
                    422,
                }:
                    self._log_failure("rejected")
                    return False
                if attempt + 1 < self.config.max_attempts:
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        break
                    await self.sleep(min(float(attempt + 1), remaining))
        self._outage_delay = min(60.0, max(float(self.config.interval), self._outage_delay * 2))
        self._next_send_at = self.clock() + self._outage_delay
        self._log_failure("transient")
        return False

    def _log_failure(self, category: str) -> None:
        if category != self._last_failure:
            logger.warning(
                "heartbeat_send_failed device_id=%s category=%s",
                self.config.device_id,
                category,
            )
            self._last_failure = category

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        try:
            value = int(response.headers.get("retry-after", ""))
        except ValueError:
            value = 0
        return float(min(300, max(0, value)))
