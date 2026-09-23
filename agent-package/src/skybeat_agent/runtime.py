"""Single-loop latest-only runtime; no persistent telemetry queue."""

import asyncio
from collections.abc import Awaitable, Callable
from random import uniform
from typing import Any

from skybeat_agent.config import Config
from skybeat_agent.telemetry import build_snapshot
from skybeat_agent.transport import HeartbeatSender


async def _await_or_stop(awaitable: Awaitable[Any], stop: asyncio.Event) -> tuple[bool, Any]:
    """Return whether work completed; cancellation is drained before shutdown continues."""
    work = asyncio.ensure_future(awaitable)
    stopped = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait({work, stopped}, return_when=asyncio.FIRST_COMPLETED)
    if stopped in done:
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        return False, None
    stopped.cancel()
    await asyncio.gather(stopped, return_exceptions=True)
    return True, work.result()


async def run(
    config: Config,
    sender: HeartbeatSender,
    *,
    system: Callable[[float], Awaitable[dict[str, Any]]],
    gpu: Callable[[], Awaitable[dict[str, Any]]],
    stop: asyncio.Event,
    jitter: Callable[[float, float], float] = uniform,
) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=max(0.0, min(3.0, jitter(0.0, 3.0))))
        return
    except TimeoutError:
        pass
    while not stop.is_set():
        completed, snapshot = await _await_or_stop(
            build_snapshot(config, system=system, gpu=gpu), stop
        )
        if not completed:
            return
        completed, _ = await _await_or_stop(sender.send(snapshot), stop)
        if not completed:
            return
        try:
            delay = max(0.0, jitter(config.interval * 0.9, config.interval * 1.1))
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            continue
