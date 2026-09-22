"""Stage 02 vertical proof: agent snapshot -> FastAPI -> real isolated MySQL."""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent" / "src"))

from skybeat_agent.config import Config
from skybeat_agent.telemetry import build_snapshot
from skybeat_agent.transport import HeartbeatSender

from app.devices.service import IdentityService
from app.main import create_app
from app.models import DeviceLatest, HeartbeatSample

pytestmark = pytest.mark.mysql


def test_real_agent_sender_persists_snapshot_through_fastapi(mysql_database, mysql_settings):
    identity = IdentityService(mysql_database, actor="agent-integration")
    project = identity.create_project("Agent integration")
    enrolled = identity.enroll(project.public_id, "Linux agent")
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://testserver",
            "SKYBEAT_DEVICE_ID": enrolled.device.device_uuid,
            "SKYBEAT_DEVICE_TOKEN": enrolled.credential.token.get_secret_value(),
            "SKYBEAT_GPU_COLLECTION_ENABLED": "false",
        }
    )
    app = create_app(mysql_settings, database=mysql_database)

    async def send() -> bool:
        async def gpu() -> dict[str, object]:
            return {
                "gpu_health": {
                    "state": "UNKNOWN",
                    "reason_code": "disabled",
                    "inventory_reliable": False,
                },
                "gpus": [],
            }

        snapshot = await build_snapshot(
            config,
            system=lambda: {
                "hostname": "integration-linux",
                "ip_addresses": ["192.0.2.20"],
                "os": {"name": "Linux", "version": None, "kernel": None, "architecture": "x86_64"},
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
        sender = HeartbeatSender(config, transport=httpx.ASGITransport(app=app))
        return await sender.send(snapshot)

    with TestClient(app):
        assert asyncio.run(send()) is True
    with mysql_database.transaction() as session:
        latest = session.get(DeviceLatest, enrolled.device.id)
        assert latest is not None
        assert latest.payload["hostname"] == "integration-linux"
        assert (
            session.scalar(
                select(func.count())
                .select_from(HeartbeatSample)
                .where(HeartbeatSample.device_id == enrolled.device.id)
            )
            == 1
        )
