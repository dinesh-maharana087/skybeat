"""Complete, independent schema-v1 examples for contract/integration tests."""


def heartbeat_payload():
    return {
        "schema_version": 1,
        "heartbeat_id": "de8308b2-0a52-4f80-9944-beb045f5e8e2",
        "device_id": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
        "agent_version": "1.0.0",
        "collected_at": "2026-09-21T10:30:00.000Z",
        "hostname": "edge-gpu-01",
        "ip_addresses": ["192.0.2.10", "2001:db8::10"],
        "os": {
            "name": "Ubuntu",
            "version": "24.04",
            "kernel": "6.8.0-example",
            "architecture": "x86_64",
        },
        "uptime_seconds": 86400,
        "cpu": {"utilization_percent": 23.5},
        "memory": {
            "total_bytes": 34359738368,
            "used_bytes": 8589934592,
            "available_bytes": 25769803776,
            "utilization_percent": 25.0,
        },
        "disks": [
            {
                "device": "/dev/nvme0n1p2",
                "mountpoint": "/",
                "filesystem": "ext4",
                "total_bytes": 107374182400,
                "used_bytes": 42949672960,
                "free_bytes": 64424509440,
                "utilization_percent": 40.0,
            }
        ],
        "gpu_health": {"state": "OK", "reason_code": None, "inventory_reliable": True},
        "gpus": [
            {
                "index": 0,
                "uuid": "GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "model": "NVIDIA RTX 4090",
                "driver_version": "example-driver",
                "utilization_percent": 35.0,
                "temperature_celsius": 62.0,
                "memory_total_bytes": 25769803776,
                "memory_used_bytes": 6442450944,
                "health": "OK",
                "reason_code": None,
            }
        ],
    }
