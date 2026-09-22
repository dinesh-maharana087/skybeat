"""Strict, bounded schema-v1 parsing for untrusted heartbeat JSON."""

import hashlib
import ipaddress
import json
import math
import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

MAX_BODY_BYTES = 128 * 1024
_REASON_CODES = {
    "no_gpu",
    "command_missing",
    "permission_denied",
    "timeout",
    "collector_stuck",
    "nonzero_exit",
    "malformed_output",
    "output_limit",
    "driver_unavailable",
    "unsupported_metric",
    "collector_error",
    "disabled",
}
_SMI_REASONS = {
    "command_missing",
    "permission_denied",
    "timeout",
    "collector_stuck",
    "nonzero_exit",
    "malformed_output",
    "output_limit",
}


class HeartbeatValidationError(ValueError):
    def __init__(
        self, status_code: int, code: str, fields: list[dict[str, str]] | None = None
    ) -> None:
        super().__init__("Heartbeat payload is invalid.")
        self.status_code = status_code
        self.code = code
        self.fields = fields or []


def _canonical_uuid(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid identifier")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise ValueError("invalid identifier") from error
    if str(parsed) != value:
        raise ValueError("invalid identifier")
    return value


def _safe_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > limit
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("invalid text")
    return value


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OperatingSystem(WireModel):
    name: str | None
    version: str | None
    kernel: str | None
    architecture: str | None

    _name = field_validator("name")(lambda value: _safe_text(value, 128))
    _version = field_validator("version")(lambda value: _safe_text(value, 128))
    _kernel = field_validator("kernel")(lambda value: _safe_text(value, 128))
    _architecture = field_validator("architecture")(lambda value: _safe_text(value, 32))


class CPU(WireModel):
    utilization_percent: float | None

    @field_validator("utilization_percent")
    @classmethod
    def valid_percent(cls, value: float | None) -> float | None:
        return _percent(value)


class Memory(WireModel):
    total_bytes: int | None
    used_bytes: int | None
    available_bytes: int | None
    utilization_percent: float | None

    @field_validator("total_bytes", "used_bytes", "available_bytes")
    @classmethod
    def valid_bytes(cls, value: int | None) -> int | None:
        return _bytes(value)

    @field_validator("utilization_percent")
    @classmethod
    def valid_percent(cls, value: float | None) -> float | None:
        return _percent(value)

    @model_validator(mode="after")
    def measurements_fit_total(self) -> "Memory":
        if self.total_bytes is not None and (
            (self.used_bytes is not None and self.used_bytes > self.total_bytes)
            or (self.available_bytes is not None and self.available_bytes > self.total_bytes)
        ):
            raise ValueError("memory exceeds total")
        return self


def _bytes(value: int | None) -> int | None:
    if value is not None and (type(value) is not int or not 0 <= value < 2**53):
        raise ValueError("invalid bytes")
    return value


def _percent(value: float | None) -> float | None:
    if value is not None and (
        type(value) not in {int, float}
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= 100
    ):
        raise ValueError("invalid percentage")
    return value


class Disk(WireModel):
    device: str | None
    mountpoint: str
    filesystem: str | None
    total_bytes: int | None
    used_bytes: int | None
    free_bytes: int | None
    utilization_percent: float | None

    _device = field_validator("device")(lambda value: _safe_text(value, 4096))
    _filesystem = field_validator("filesystem")(lambda value: _safe_text(value, 64))

    @field_validator("total_bytes", "used_bytes", "free_bytes")
    @classmethod
    def disk_bytes(cls, value: int | None) -> int | None:
        return _bytes(value)

    _percent = field_validator("utilization_percent")(_percent)

    @field_validator("mountpoint")
    @classmethod
    def valid_mountpoint(cls, value: str) -> str:
        if not isinstance(value, str) or not value.startswith("/") or len(value) > 4096:
            raise ValueError("invalid mountpoint")
        _safe_text(value, 4096)
        return value


class GPUHealth(WireModel):
    state: Literal["OK", "GPU_MISSING", "NVIDIA_SMI_FAILED", "DRIVER_ERROR", "UNKNOWN"]
    reason_code: str | None
    inventory_reliable: bool

    @field_validator("reason_code")
    @classmethod
    def valid_reason(cls, value: str | None) -> str | None:
        if value is not None and value not in _REASON_CODES:
            raise ValueError("invalid reason")
        return value


class GPU(WireModel):
    index: int
    uuid: str | None
    model: str | None
    driver_version: str | None
    utilization_percent: float | None
    temperature_celsius: float | None
    memory_total_bytes: int | None
    memory_used_bytes: int | None
    health: Literal["OK", "GPU_MISSING", "NVIDIA_SMI_FAILED", "DRIVER_ERROR", "UNKNOWN"]
    reason_code: str | None

    _uuid = field_validator("uuid")(lambda value: _safe_text(value, 96))
    _model = field_validator("model")(lambda value: _safe_text(value, 256))
    _driver = field_validator("driver_version")(lambda value: _safe_text(value, 128))
    _percent = field_validator("utilization_percent")(_percent)

    @field_validator("memory_total_bytes", "memory_used_bytes")
    @classmethod
    def gpu_bytes(cls, value: int | None) -> int | None:
        return _bytes(value)

    @field_validator("index")
    @classmethod
    def valid_index(cls, value: int) -> int:
        if type(value) is not int or not 0 <= value <= 1023:
            raise ValueError("invalid gpu index")
        return value

    @field_validator("temperature_celsius")
    @classmethod
    def valid_temperature(cls, value: float | None) -> float | None:
        if value is not None and (
            type(value) not in {int, float}
            or isinstance(value, bool)
            or not math.isfinite(value)
            or not -100 <= value <= 250
        ):
            raise ValueError("invalid temperature")
        return value

    @field_validator("reason_code")
    @classmethod
    def valid_reason(cls, value: str | None) -> str | None:
        if value is not None and value not in _REASON_CODES:
            raise ValueError("invalid reason")
        return value


class Heartbeat(WireModel):
    schema_version: Literal[1]
    heartbeat_id: str
    device_id: str
    agent_version: str
    collected_at: datetime
    hostname: str
    ip_addresses: list[str] = Field(max_length=16)
    os: OperatingSystem
    uptime_seconds: float | None
    cpu: CPU
    memory: Memory
    disks: list[Disk] = Field(max_length=64)
    gpu_health: GPUHealth
    gpus: list[GPU] = Field(max_length=64)

    _heartbeat = field_validator("heartbeat_id")(_canonical_uuid)
    _device = field_validator("device_id")(_canonical_uuid)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_schema_version(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("unsupported schema version")
        return value

    @field_validator("agent_version")
    @classmethod
    def valid_agent_version(cls, value: str) -> str:
        result = _safe_text(value, 64)
        if not result:
            raise ValueError("empty version")
        return result

    @field_validator("hostname")
    @classmethod
    def valid_hostname(cls, value: str) -> str:
        result = _safe_text(value, 253)
        if not result:
            raise ValueError("empty hostname")
        return result

    @field_validator("collected_at", mode="before")
    @classmethod
    def utc_timestamp(cls, value: object) -> datetime:
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
        ):
            raise ValueError("timestamp must be UTC")
        try:
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            return datetime.fromisoformat(normalized).astimezone(UTC)
        except ValueError as error:
            raise ValueError("timestamp must be UTC") from error

    @field_validator("ip_addresses")
    @classmethod
    def valid_ips(cls, values: list[str]) -> list[str]:
        canonical: list[str] = []
        for value in values:
            if not isinstance(value, str) or "%" in value:
                raise ValueError("invalid IP")
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError as error:
                raise ValueError("invalid IP") from error
            normalized = str(parsed)
            if normalized in canonical:
                raise ValueError("duplicate IP")
            canonical.append(normalized)
        return canonical

    @field_validator("uptime_seconds")
    @classmethod
    def valid_uptime(cls, value: float | None) -> float | None:
        if value is not None and (
            type(value) not in {int, float}
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("invalid uptime")
        return value

    @model_validator(mode="after")
    def valid_gpu_inventory(self) -> "Heartbeat":
        mountpoints = [disk.mountpoint for disk in self.disks]
        if len(mountpoints) != len(set(mountpoints)):
            raise ValueError("duplicate mountpoint")
        indexes = [gpu.index for gpu in self.gpus]
        uuids = [gpu.uuid for gpu in self.gpus if gpu.uuid is not None]
        if len(indexes) != len(set(indexes)) or len(uuids) != len(set(uuids)):
            raise ValueError("duplicate GPU identity")
        health = self.gpu_health
        if health.state == "OK":
            valid = health.reason_code is None and health.inventory_reliable and bool(self.gpus)
        elif health.state == "GPU_MISSING":
            valid = health.reason_code == "no_gpu" and health.inventory_reliable and not self.gpus
        elif health.state == "NVIDIA_SMI_FAILED":
            valid = (
                health.reason_code in _SMI_REASONS
                and not health.inventory_reliable
                and not self.gpus
            )
        elif health.state == "DRIVER_ERROR":
            valid = (
                health.reason_code == "driver_unavailable"
                and not health.inventory_reliable
                and not self.gpus
            )
        elif health.reason_code == "unsupported_metric":
            valid = health.inventory_reliable and bool(self.gpus)
        else:
            valid = (
                health.reason_code in {"collector_error", "disabled"}
                and not health.inventory_reliable
                and not self.gpus
            )
        if not valid:
            raise ValueError("contradictory GPU inventory")
        return self


class _DuplicateKey(ValueError):
    pass


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey()
        result[key] = value
    return result


def _reject_constants(_: str) -> None:
    raise ValueError("non-finite number")


def _check_json(value: Any, depth: int = 0) -> None:
    if depth > 8:
        raise HeartbeatValidationError(400, "invalid_json")
    if isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise HeartbeatValidationError(400, "invalid_json")
    if isinstance(value, float) and not math.isfinite(value):
        raise HeartbeatValidationError(400, "invalid_json")
    if isinstance(value, dict):
        for key, child in value.items():
            _check_json(key, depth + 1)
            _check_json(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_json(child, depth + 1)


def parse_heartbeat(raw: bytes) -> Heartbeat:
    if len(raw) > MAX_BODY_BYTES:
        raise HeartbeatValidationError(413, "payload_too_large")
    try:
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_object_pairs, parse_constant=_reject_constants
        )
        if not isinstance(payload, dict):
            raise ValueError("root")
        _check_json(payload)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _DuplicateKey,
        ValueError,
        HeartbeatValidationError,
    ) as error:
        if isinstance(error, HeartbeatValidationError):
            raise
        raise HeartbeatValidationError(400, "invalid_json") from None
    try:
        return Heartbeat.model_validate(payload)
    except ValidationError as error:
        fields = [{"path": "payload", "code": "invalid"} for _ in error.errors()[:16]]
        raise HeartbeatValidationError(422, "validation_error", fields) from None


def normalized_payload(heartbeat: Heartbeat) -> dict[str, Any]:
    return heartbeat.model_dump(mode="json")


def payload_digest(heartbeat: Heartbeat) -> bytes:
    encoded = json.dumps(
        normalized_payload(heartbeat), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(encoded.encode("ascii")).digest()
