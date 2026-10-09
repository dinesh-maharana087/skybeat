"""Independent bounded Log Watch upload; no persistent local queue."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

import httpx

from skybeat_agent.collectors.logs import MAX_UPLOAD_ENTRIES, SOURCES, JournalCollector
from skybeat_agent.config import Config

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 72 * 1024


class LogSender:
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

    async def send(self, payload: dict[str, Any]) -> bool:
        if self.clock() < self._next_send_at:
            return False
        bounded = {**payload, "entries": list(payload["entries"])[-MAX_UPLOAD_ENTRIES:]}
        raw = json.dumps(bounded, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        while len(raw) > MAX_BODY_BYTES and bounded["entries"]:
            bounded["entries"].pop(0)
            raw = json.dumps(bounded, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(raw) > MAX_BODY_BYTES:
            return False
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(transport=self.transport, follow_redirects=False) as client:
            for attempt in range(2):
                try:
                    response = await asyncio.wait_for(
                        client.post(
                            f"{self.config.server_url}/api/v1/agent/logs",
                            content=raw,
                            headers=headers,
                            timeout=httpx.Timeout(5.0, connect=3.0),
                        ),
                        timeout=5.0,
                    )
                except (TimeoutError, httpx.HTTPError):
                    response = None
                if response is not None and response.status_code == 200:
                    return True
                if response is not None and response.status_code in {401, 403}:
                    self._next_send_at = self.clock() + 300
                    return False
                if response is not None and response.status_code == 429:
                    self._next_send_at = self.clock() + self._retry_after(response)
                    return False
                if response is not None and response.status_code in {400, 404, 413, 415, 422}:
                    return False
                if attempt == 0:
                    await self.sleep(1)
        return False

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        try:
            seconds = int(response.headers.get("retry-after", ""))
        except ValueError:
            seconds = 1
        return float(min(300, max(1, seconds)))


class LogWatchPublisher:
    def __init__(
        self,
        collector: JournalCollector,
        sender: LogSender,
        *,
        sources: tuple[str, ...] = SOURCES,
    ) -> None:
        self.collector = collector
        self.sender = sender
        self.sources = sources

    async def run_once(self) -> None:
        for source in self.sources:
            try:
                payload = await self.collector.collect(source)
                sent = await self.sender.send(payload)
                if not sent:
                    logger.warning("log_watch_upload_failed source=%s", source)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "log_watch_source_failed source=%s category=%s", source, type(error).__name__
                )
