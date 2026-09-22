"""psutil-based system telemetry without shelling out or inspecting user data."""

import asyncio
import ipaddress
import platform
import socket
import time
from collections.abc import Callable
from multiprocessing import get_context
from multiprocessing.connection import Connection
from typing import Any

import psutil

PROCESS_POLL_SECONDS = 0.01
PROCESS_TERMINATE_GRACE_SECONDS = 1.0
PROCESS_KILL_GRACE_SECONDS = 1.0


class SystemCollectionError(Exception):
    """A safe, categorical error raised by the bounded system collector."""


def _collect_in_child(connection: Connection, collector: Callable[[], dict[str, Any]]) -> None:
    try:
        connection.send(("result", collector()))
    except BaseException as error:
        try:
            connection.send(("error", type(error).__name__))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


class BoundedSystemCollector:
    """Run a synchronous collector in a killable process, never an executor thread."""

    def __init__(self, collector: Callable[[], dict[str, Any]]) -> None:
        self._collector = collector

    async def collect(self, timeout: float) -> dict[str, Any]:
        parent, child = get_context("spawn").Pipe(duplex=False)
        process = get_context("spawn").Process(
            target=_collect_in_child,
            args=(child, self._collector),
            daemon=True,
        )
        try:
            process.start()
            child.close()
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while loop.time() < deadline:
                if parent.poll():
                    outcome, payload = parent.recv()
                    if outcome == "result" and isinstance(payload, dict):
                        return payload
                    raise SystemCollectionError("collector_error")
                if not process.is_alive():
                    raise SystemCollectionError("collector_exited")
                await asyncio.sleep(min(PROCESS_POLL_SECONDS, max(0.0, deadline - loop.time())))
            raise SystemCollectionError("timeout")
        finally:
            parent.close()
            if process.is_alive():
                process.terminate()
                process.join(PROCESS_TERMINATE_GRACE_SECONDS)
            if process.is_alive():
                process.kill()
                process.join(PROCESS_KILL_GRACE_SECONDS)
            if not process.is_alive():
                process.close()


def prime_cpu_sample() -> None:
    """Discard psutil's initial nonblocking sample before the first heartbeat."""
    try:
        psutil.cpu_percent(interval=None)
    except (OSError, psutil.Error):
        pass


def _operating_system() -> dict[str, str | None]:
    try:
        release = platform.freedesktop_os_release()
        name = release.get("NAME") or None
        version = release.get("VERSION_ID") or None
    except (AttributeError, OSError):
        name = None
        version = None
    try:
        kernel = platform.release() or None
    except OSError:
        kernel = None
    try:
        architecture = platform.machine() or None
    except OSError:
        architecture = None
    return {"name": name, "version": version, "kernel": kernel, "architecture": architecture}


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
        "os": _operating_system(),
        "uptime_seconds": uptime,
        "cpu": {"utilization_percent": cpu},
        "memory": memory_data,
        "disks": disks,
    }
