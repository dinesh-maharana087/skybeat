"""Immutable schema-v1 snapshot construction."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from skybeat_agent.config import Config


async def build_snapshot(
    config: Config,
    *,
    system: Callable[[], dict[str, Any]],
    gpu: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    host = system()
    gpu_data = await gpu()
    return {
        "schema_version": 1,
        "heartbeat_id": str(uuid4()),
        "device_id": config.device_id,
        "agent_version": "1.0.0",
        "collected_at": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        **host,
        **gpu_data,
    }
