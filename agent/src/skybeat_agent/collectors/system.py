"""psutil-based system telemetry without shelling out or inspecting user data."""

import ipaddress
import platform
import socket
import time
from typing import Any

import psutil


def collect_system(mountpoints: tuple[str, ...]) -> dict[str, Any]:
    try:
        hostname = socket.gethostname()
    except OSError:
        hostname = "unknown"
    ips: set[str] = set()
    try:
        for rows in psutil.net_if_addrs().values():
            for row in rows:
                try:
                    address = ipaddress.ip_address(row.address.split("%", 1)[0])
                    if not (address.is_loopback or address.is_unspecified or address.is_multicast):
                        ips.add(str(address))
                except ValueError:
                    continue
    except (OSError, psutil.Error):
        pass
    try:
        memory = psutil.virtual_memory()
        memory_data: dict[str, int | float | None] = {
            "total_bytes": memory.total,
            "used_bytes": memory.used,
            "available_bytes": memory.available,
            "utilization_percent": memory.percent,
        }
    except (OSError, psutil.Error):
        memory_data = {
            "total_bytes": None,
            "used_bytes": None,
            "available_bytes": None,
            "utilization_percent": None,
        }
    disks = []
    for mount in mountpoints:
        try:
            usage = psutil.disk_usage(mount)
            disks.append(
                {
                    "device": None,
                    "mountpoint": mount,
                    "filesystem": None,
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "utilization_percent": usage.percent,
                }
            )
        except (OSError, psutil.Error):
            disks.append(
                {
                    "device": None,
                    "mountpoint": mount,
                    "filesystem": None,
                    "total_bytes": None,
                    "used_bytes": None,
                    "free_bytes": None,
                    "utilization_percent": None,
                }
            )
    try:
        uptime: float | None = max(0, time.time() - psutil.boot_time())
    except (OSError, psutil.Error):
        uptime = None
    try:
        cpu: float | None = psutil.cpu_percent(interval=None)
    except (OSError, psutil.Error):
        cpu = None
    return {
        "hostname": hostname[:253],
        "ip_addresses": sorted(ips)[:16],
        "os": {
            "name": platform.system() or None,
            "version": platform.release() or None,
            "kernel": platform.version() or None,
            "architecture": platform.machine() or None,
        },
        "uptime_seconds": uptime,
        "cpu": {"utilization_percent": cpu},
        "memory": memory_data,
        "disks": disks,
    }
