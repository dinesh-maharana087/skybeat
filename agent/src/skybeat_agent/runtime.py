"""Single-loop latest-only runtime; no persistent telemetry queue."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from skybeat_agent.config import Config
from skybeat_agent.telemetry import build_snapshot
from skybeat_agent.transport import HeartbeatSender


async def run(
    config: Config,
    sender: HeartbeatSender,
    *,
    system: Callable[[], dict[str, Any]],
    gpu: Callable[[], Awaitable[dict[str, Any]]],
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        snapshot = await build_snapshot(config, system=system, gpu=gpu)
        await sender.send(snapshot)
        try:
            await asyncio.wait_for(stop.wait(), timeout=config.interval)
        except TimeoutError:
            continue
