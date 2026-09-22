import asyncio

from skybeat_agent.config import Config
from skybeat_agent.telemetry import build_snapshot


def test_snapshot_preserves_zero_and_is_immutable():
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )

    async def collect():
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
            system=lambda: {
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
            },
            gpu=gpu,
        )

    snapshot = asyncio.run(collect())
    assert snapshot["device_id"] == config.device_id
    assert snapshot["cpu"]["utilization_percent"] == 0
    assert snapshot["heartbeat_id"]
