"""Immutable schema-v1 snapshot construction."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from skybeat_agent.collectors.system import BoundedSystemCollector
from skybeat_agent.config import Config

SYSTEM_COLLECTION_TIMEOUT_SECONDS = 3.0
logger = logging.getLogger(__name__)


def unavailable_system() -> dict[str, Any]:
    return {
        "hostname": "unknown",
        "ip_addresses": [],
        "os": {"name": None, "version": None, "kernel": None, "architecture": None},
        "uptime_seconds": None,
        "cpu": {"utilization_percent": None},
        "memory": {
            "total_bytes": None,
            "used_bytes": None,
            "available_bytes": None,
            "utilization_percent": None,
        },
        "disks": [],
    }


async def build_snapshot(
    config: Config,
    *,
    system: Callable[[float], Awaitable[dict[str, Any]]],
    gpu: Callable[[], Awaitable[dict[str, Any]]],
    system_timeout: float = SYSTEM_COLLECTION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        host = await system(system_timeout)
    except Exception as error:
        logger.warning(
            "collector_failed component=system category=system_collection_error exception_type=%s",
            type(error).__name__,
        )
        host = unavailable_system()
    try:
        gpu_data = await asyncio.wait_for(gpu(), timeout=config.nvidia_smi_timeout)
    except Exception as error:
        logger.warning(
            "collector_failed component=gpu category=collector_error exception_type=%s",
            type(error).__name__,
        )
        gpu_data = {
            "gpu_health": {
                "state": "UNKNOWN",
                "reason_code": "collector_error",
                "inventory_reliable": False,
            },
            "gpus": [],
        }
    return {
        "schema_version": 1,
        "heartbeat_id": str(uuid4()),
        "device_id": config.device_id,
        "agent_version": "1.0.0",
        "collected_at": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        **host,
        **gpu_data,
    }


def bounded_system_collector(
    collector: Callable[[], dict[str, Any]],
) -> Callable[[float], Awaitable[dict[str, Any]]]:
    bounded = BoundedSystemCollector(collector)
    return bounded.collect
