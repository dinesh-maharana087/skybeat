from datetime import UTC, datetime
from types import SimpleNamespace

from app.dashboard.read import device_view


def test_device_view_preserves_nulls_multiple_inventory_and_marks_offline_telemetry_stale():
    latest = SimpleNamespace(
        hostname="<img src=x onerror=alert(1)>",
        primary_ip="192.0.2.10",
        agent_version="1.0.0",
        received_at=datetime(2026, 9, 23, 10, 0),
        collected_at=datetime(2026, 9, 23, 9, 59),
        cpu_percent=None,
        memory_percent=None,
        disk_summary={"items": [{"mountpoint": "/"}, {"mountpoint": "/data"}]},
        gpu_summary={"state": "OK"},
        payload={
            "ip_addresses": ["192.0.2.10"],
            "uptime_seconds": None,
            "os": {"name": "Ubuntu"},
            "memory": {"total_bytes": None, "used_bytes": None},
            "disks": [{"mountpoint": "/"}, {"mountpoint": "/data"}],
            "gpu_health": {"state": "OK"},
            "gpus": [{"index": 0}, {"index": 1}],
        },
    )
    device = SimpleNamespace(
        device_uuid="65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
        name="<script>alert(1)</script>",
        monitoring_enabled=True,
        last_seen_at=datetime(2026, 9, 23, 10, 0),
        availability_state="OFFLINE",
        gpu_monitoring_enabled=True,
        gpu_effective_state="DRIVER_ERROR",
        expected_gpu_min_count=2,
        expected_gpu_uuids=["GPU-one", "GPU-two"],
    )
    project = SimpleNamespace(public_id="e3e70682-c209-4cac-a29f-6fbed82c07cd", name="Project")

    view = device_view(device, project, latest, datetime(2026, 9, 23, 10, 10, tzinfo=UTC))

    assert view["state"] == "OFFLINE"
    assert view["telemetry_stale"] is True
    assert view["name"] == "<script>alert(1)</script>"
    assert view["cpu"]["utilization_percent"] is None
    assert view["memory"]["total_bytes"] is None
    assert len(view["disks"]) == 2
    assert len(view["gpus"]) == 2
    assert view["gpu_health"]["effective"] == "DRIVER_ERROR"


def test_device_view_uses_awaiting_first_heartbeat_without_fabricating_telemetry():
    device = SimpleNamespace(
        device_uuid="65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
        name="New device",
        monitoring_enabled=True,
        last_seen_at=None,
        availability_state="ONLINE",
        gpu_monitoring_enabled=False,
        gpu_effective_state="OK",
        expected_gpu_min_count=0,
        expected_gpu_uuids=[],
    )
    project = SimpleNamespace(public_id="e3e70682-c209-4cac-a29f-6fbed82c07cd", name="Project")

    view = device_view(device, project, None, datetime(2026, 9, 23, 10, 10, tzinfo=UTC))

    assert view["state"] == "AWAITING_FIRST_HEARTBEAT"
    assert view["hostname"] is None
    assert view["cpu"] is None
    assert view["disks"] == []
    assert view["gpus"] == []
    assert view["gpu_health"]["effective"] == "NOT MONITORED"
