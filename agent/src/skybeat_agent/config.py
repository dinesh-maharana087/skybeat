"""Validated, immutable agent configuration with secret-safe representation."""

import re
from dataclasses import dataclass, field
from os import environ
from urllib.parse import urlsplit
from uuid import UUID


class ConfigurationError(ValueError):
    """A safe configuration error that deliberately excludes supplied values."""


def _integer(env: dict[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ConfigurationError(f"{name} is invalid.") from None
    if str(value) != raw or not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} is invalid.")
    return value


def _boolean(env: dict[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, str(default).lower()).lower()
    if raw not in {"true", "false"}:
        raise ConfigurationError(f"{name} is invalid.")
    return raw == "true"


@dataclass(frozen=True)
class Config:
    server_url: str
    device_id: str
    token: str = field(repr=False)
    interval: int = 30
    request_timeout: int = 10
    connect_timeout: int = 3
    max_attempts: int = 3
    gpu_collection_enabled: bool = True
    nvidia_smi_path: str = "/usr/bin/nvidia-smi"
    nvidia_smi_timeout: int = 5
    mountpoints: tuple[str, ...] = ("/",)
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, values: dict[str, str] | None = None) -> "Config":
        env = dict(environ if values is None else values)
        required = ("SKYBEAT_SERVER_URL", "SKYBEAT_DEVICE_ID", "SKYBEAT_DEVICE_TOKEN")
        if any(not env.get(name) for name in required):
            raise ConfigurationError("Required SkyBeat configuration is missing.")
        server_url = env["SKYBEAT_SERVER_URL"]
        parsed = urlsplit(server_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError("SKYBEAT_SERVER_URL is invalid.")
        server_url = server_url.rstrip("/")
        device_id = env["SKYBEAT_DEVICE_ID"]
        try:
            if str(UUID(device_id)) != device_id:
                raise ValueError
        except ValueError:
            raise ConfigurationError("SKYBEAT_DEVICE_ID is invalid.") from None
        token = env["SKYBEAT_DEVICE_TOKEN"]
        if not re.fullmatch(
            r"sb1\.[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\.[A-Za-z0-9_-]{43}", token
        ):
            raise ConfigurationError("SKYBEAT_DEVICE_TOKEN is invalid.")
        mounts = tuple(part.strip() for part in env.get("SKYBEAT_DISK_MOUNTPOINTS", "/").split(","))
        if (
            not mounts
            or len(mounts) > 64
            or len(set(mounts)) != len(mounts)
            or any(not mount.startswith("/") or "\x00" in mount for mount in mounts)
        ):
            raise ConfigurationError("SKYBEAT_DISK_MOUNTPOINTS is invalid.")
        path = env.get("SKYBEAT_NVIDIA_SMI_PATH", "/usr/bin/nvidia-smi")
        if not path.startswith("/") or "\x00" in path:
            raise ConfigurationError("SKYBEAT_NVIDIA_SMI_PATH is invalid.")
        level = env.get("SKYBEAT_LOG_LEVEL", "INFO").upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("SKYBEAT_LOG_LEVEL is invalid.")
        return cls(
            server_url=server_url,
            device_id=device_id,
            token=token,
            interval=_integer(env, "SKYBEAT_HEARTBEAT_INTERVAL_SECONDS", 30, 1, 3600),
            request_timeout=_integer(env, "SKYBEAT_REQUEST_TIMEOUT_SECONDS", 10, 1, 30),
            connect_timeout=_integer(env, "SKYBEAT_CONNECT_TIMEOUT_SECONDS", 3, 1, 10),
            max_attempts=_integer(env, "SKYBEAT_MAX_SEND_ATTEMPTS", 3, 1, 3),
            gpu_collection_enabled=_boolean(env, "SKYBEAT_GPU_COLLECTION_ENABLED", True),
            nvidia_smi_path=path,
            nvidia_smi_timeout=_integer(env, "SKYBEAT_NVIDIA_SMI_TIMEOUT_SECONDS", 5, 1, 10),
            mountpoints=mounts,
            log_level=level,
        )
