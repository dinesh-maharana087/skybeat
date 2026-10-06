"""Independent bounded Log Watch upload; no persistent local queue."""

import asyncio
import json
import logging
from typing import Any

import httpx

from skybeat_agent.collectors.logs import SOURCES, JournalCollector
from skybeat_agent.config import Config

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 72 * 1024


class LogSender:
    def __init__(
        self, config: Config, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self.transport = transport
        self._credential_retry_at = 0.0

    async def send(self, payload: dict[str, Any]) -> bool:
        if asyncio.get_running_loop().time() < self._credential_retry_at:
            return False
        bounded = {**payload, "entries": list(payload["entries"])}
        raw = json.dumps(bounded, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        while len(raw) > MAX_BODY_BYTES and bounded["entries"]:
            bounded["entries"].pop(0)
            raw = json.dumps(bounded, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
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
                    self._credential_retry_at = asyncio.get_running_loop().time() + 300
                    return False
                if response is not None and response.status_code in {400, 404, 413, 415, 422, 429}:
                    return False
                if attempt == 0:
                    await asyncio.sleep(1)
        return False


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
