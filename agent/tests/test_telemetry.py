import asyncio
import time

from skybeat_agent.collectors.system import BoundedSystemCollector
from skybeat_agent.config import Config
from skybeat_agent.telemetry import build_snapshot


def _slow_system() -> dict[str, object]:
    time.sleep(1)
    return {}


def test_snapshot_preserves_zero_and_is_immutable():
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )

    async def collect():
        async def system(_: float):
            return {
                "hostname": "edge",
                "ip_addresses": [],
                "os": {"name": None, "version": None, "kernel": None, "architecture": None},
                "uptime_seconds": 0,
                "cpu": {"utilization_percent": 0},
                "memory": {
                    "total_bytes": 0,
                    "used_bytes": 0,
                    "available_bytes": 0,
                    "utilization_percent": 0,
                },
                "disks": [],
            }

        async def gpu():
            return {
                "gpu_health": {
                    "state": "UNKNOWN",
                    "reason_code": "disabled",
                    "inventory_reliable": False,
                },
                "gpus": [],
            }

        return await build_snapshot(
            config,
            system=system,
            gpu=gpu,
        )

    snapshot = asyncio.run(collect())
    assert snapshot["device_id"] == config.device_id
    assert snapshot["cpu"]["utilization_percent"] == 0
    assert snapshot["heartbeat_id"]


def test_snapshot_continues_with_null_host_metrics_after_system_collection_deadline():
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )

    async def gpu():
        return {
            "gpu_health": {
                "state": "GPU_MISSING",
                "reason_code": "no_gpu",
                "inventory_reliable": True,
            },
            "gpus": [],
        }

    async def collect():
        return await build_snapshot(
            config,
            system=BoundedSystemCollector(_slow_system).collect,
            gpu=gpu,
            system_timeout=0.01,
        )

    snapshot = asyncio.run(collect())
    assert snapshot["hostname"] == "unknown"
    assert snapshot["memory"]["total_bytes"] is None
    assert snapshot["gpu_health"]["state"] == "GPU_MISSING"


def test_snapshot_keeps_system_telemetry_when_gpu_collector_raises():
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )

    async def gpu():
        raise RuntimeError("collector failed")

    async def system(_: float):
        return {
            "hostname": "edge",
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

    snapshot = asyncio.run(
        build_snapshot(
            config,
            system=system,
            gpu=gpu,
        )
    )

    assert snapshot["hostname"] == "edge"
    assert snapshot["gpu_health"] == {
        "state": "UNKNOWN",
        "reason_code": "collector_error",
        "inventory_reliable": False,
    }
