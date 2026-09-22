"""Strict heartbeat boundary tests using real JSON and model validation."""

import copy
import json
from datetime import UTC, datetime

import pytest

from app.schemas.heartbeat import (
    HeartbeatValidationError,
    normalized_payload,
    parse_heartbeat,
    payload_digest,
)
from tests.heartbeat_fixtures import heartbeat_payload


def encode(payload):
    return json.dumps(payload).encode("utf-8")


def replace(payload, path, value):
    parts = path.split(".")
    target = payload
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    target[parts[-1]] = value


def test_approved_example_preserves_identity_and_collected_at():
    heartbeat = parse_heartbeat(encode(heartbeat_payload()))
    assert heartbeat.device_id == "a4f82a6d-61c6-4c72-9a57-626e524571e4"
    assert heartbeat.collected_at == datetime(2026, 9, 21, 10, 30, tzinfo=UTC)
    assert heartbeat.memory.total_bytes == 34359738368
    assert heartbeat.gpus[0].uuid == "GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_minimum_payload_preserves_null_as_distinct_from_zero():
    payload = heartbeat_payload()
    payload["ip_addresses"] = []
    payload["disks"] = []
    payload["gpus"] = []
    payload["gpu_health"] = {
        "state": "UNKNOWN",
        "reason_code": "disabled",
        "inventory_reliable": False,
    }
    payload["uptime_seconds"] = None
    payload["os"] = dict.fromkeys(payload["os"])
    payload["cpu"]["utilization_percent"] = None
    payload["memory"] = dict.fromkeys(payload["memory"])
    result = normalized_payload(parse_heartbeat(encode(payload)))
    assert result["uptime_seconds"] is None
    assert result["cpu"]["utilization_percent"] is None
    payload["cpu"]["utilization_percent"] = 0
    measured = parse_heartbeat(encode(payload))
    assert measured.cpu.utilization_percent == 0
    assert payload_digest(measured) != payload_digest(parse_heartbeat(encode(result)))


@pytest.mark.parametrize("raw", [b"", b"{", b"{} {}", b"[]", b"null", b"1", b'"a"'])
def test_malformed_or_non_object_json_is_rejected(raw):
    with pytest.raises(HeartbeatValidationError) as result:
        parse_heartbeat(raw)
    assert result.value.status_code == 400
    assert result.value.code == "invalid_json"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"hostname":"x","hostname":"y"}',
        b'{"os":{"name":"x","name":"y"}}',
        b'{"hostname":"\xff"}',
        b'{"hostname":"\\ud800"}',
        b'{"\\udfff":"x"}',
        b'{"uptime_seconds":NaN}',
        b'{"uptime_seconds":Infinity}',
        b'{"uptime_seconds":-Infinity}',
        b'{"uptime_seconds":1e400}',
        b'{"x":' + b"[" * 8 + b"0" + b"]" * 8 + b"}",
        b"\xef\xbb\xbf{}",
    ],
)
def test_ambiguous_or_unsafe_json_is_rejected(raw):
    with pytest.raises(HeartbeatValidationError) as result:
        parse_heartbeat(raw)
    assert result.value.status_code == 400


def test_maximum_body_is_accepted_and_one_extra_byte_is_rejected():
    raw = encode(heartbeat_payload())
    padded = raw + b" " * (128 * 1024 - len(raw))
    assert parse_heartbeat(padded).schema_version == 1
    with pytest.raises(HeartbeatValidationError) as result:
        parse_heartbeat(padded + b" ")
    assert result.value.status_code == 413
    assert result.value.code == "payload_too_large"


def test_approved_json_safe_byte_limit_is_not_restricted_by_hardware_assumptions():
    payload = heartbeat_payload()
    maximum = 2**53 - 1
    payload["disks"][0].update(total_bytes=maximum, used_bytes=maximum, free_bytes=maximum)
    payload["gpus"][0].update(memory_total_bytes=maximum, memory_used_bytes=maximum)
    heartbeat = parse_heartbeat(encode(payload))
    assert heartbeat.disks[0].total_bytes == maximum
    assert heartbeat.gpus[0].memory_total_bytes == maximum


@pytest.mark.parametrize("path", ["", "os", "cpu", "memory", "disks.0", "gpus.0", "gpu_health"])
def test_unknown_fields_are_rejected_without_echoing_the_unknown_key(path):
    payload = heartbeat_payload()
    secret_key = "injected-secret-value"
    replace(payload, (path + "." if path else "") + secret_key, "secret-data")
    with pytest.raises(HeartbeatValidationError) as result:
        parse_heartbeat(encode(payload))
    assert result.value.status_code == 422
    assert secret_key not in str(result.value)
    assert secret_key not in json.dumps(result.value.fields)
    assert "secret-data" not in json.dumps(result.value.fields)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("schema_version", 1.0),
        ("heartbeat_id", "not-a-uuid"),
        ("device_id", "A4F82A6D-61C6-4C72-9A57-626E524571E4"),
        ("device_id", "{a4f82a6d-61c6-4c72-9a57-626e524571e4}"),
        ("agent_version", ""),
        ("agent_version", "v" * 65),
        ("hostname", "x" * 254),
        ("hostname", "host\nname"),
        ("collected_at", "2026-09-21"),
        ("collected_at", "2026-09-21T10:30:00"),
        ("collected_at", "2026-09-21T10:30:00+05:30"),
        ("collected_at", "2026-02-30T10:30:00Z"),
        ("collected_at", 1234),
        ("ip_addresses", ["example.com"]),
        ("ip_addresses", ["127.0.0.1:80"]),
        ("ip_addresses", ["fe80::1%eth0"]),
        ("ip_addresses", ["192.0.2.10"] * 2),
        ("ip_addresses", ["2001:db8::1", "2001:db8:0:0:0:0:0:1"]),
        ("ip_addresses", [f"192.0.2.{i}" for i in range(17)]),
        ("os.name", "x" * 129),
        ("os.version", "x" * 129),
        ("os.kernel", "x" * 129),
        ("os.architecture", "x" * 33),
        ("uptime_seconds", -1),
        ("uptime_seconds", True),
        ("uptime_seconds", "12"),
        ("cpu.utilization_percent", -0.1),
        ("cpu.utilization_percent", 100.1),
        ("cpu.utilization_percent", False),
        ("cpu.utilization_percent", "25.5"),
        ("memory.total_bytes", -1),
        ("memory.total_bytes", 2**53),
        ("memory.used_bytes", 34359738369),
        ("memory.available_bytes", 34359738369),
        ("memory.used_bytes", True),
        ("memory.utilization_percent", 101),
        ("disks.0.mountpoint", ""),
        ("disks.0.mountpoint", "relative/path"),
        ("disks.0.mountpoint", "/bad\x00path"),
        ("disks.0.device", "x" * 4097),
        ("disks.0.filesystem", "x" * 65),
        ("disks.0.mountpoint", "/" + "x" * 4096),
        ("disks.0.used_bytes", 2**53),
        ("disks.0.free_bytes", 2**53),
        ("gpus.0.index", -1),
        ("gpus.0.index", 1024),
        ("gpus.0.index", True),
        ("gpus.0.index", 1.0),
        ("gpus.0.uuid", "x" * 97),
        ("gpus.0.model", "x" * 257),
        ("gpus.0.driver_version", "x" * 129),
        ("gpus.0.temperature_celsius", -100.1),
        ("gpus.0.temperature_celsius", 250.1),
        ("gpus.0.memory_used_bytes", 2**53),
        ("gpus.0.health", "healthy"),
        ("gpus.0.reason_code", "unexpected command output"),
        ("gpu_health.inventory_reliable", 1),
        ("gpu_health.reason_code", "timeout"),
        ("gpu_health.state", "NOT MONITORED"),
    ],
)
def test_invalid_contract_fields_are_rejected(path, value):
    payload = heartbeat_payload()
    replace(payload, path, value)
    with pytest.raises(HeartbeatValidationError) as result:
        parse_heartbeat(encode(payload))
    assert result.value.status_code == 422
    assert result.value.code == "validation_error"


@pytest.mark.parametrize("field", list(heartbeat_payload()))
def test_all_documented_top_level_fields_are_required(field):
    payload = heartbeat_payload()
    del payload[field]
    with pytest.raises(HeartbeatValidationError):
        parse_heartbeat(encode(payload))


@pytest.mark.parametrize("kind", ["mountpoint", "gpu_uuid", "gpu_index"])
def test_duplicate_mounts_and_gpu_identities_are_rejected(kind):
    payload = heartbeat_payload()
    if kind == "mountpoint":
        payload["disks"].append(copy.deepcopy(payload["disks"][0]))
    else:
        row = copy.deepcopy(payload["gpus"][0])
        if kind == "gpu_uuid":
            row["index"] = 1
        else:
            row["uuid"] = "GPU-bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"
        payload["gpus"].append(row)
    with pytest.raises(HeartbeatValidationError):
        parse_heartbeat(encode(payload))


@pytest.mark.parametrize("field", ["disks", "gpus"])
def test_inventory_row_limit(field):
    payload = heartbeat_payload()
    source = payload[field][0]
    payload[field] = []
    for index in range(64):
        row = copy.deepcopy(source)
        if field == "disks":
            row["mountpoint"] = f"/mount/{index}"
        else:
            row["uuid"] = f"GPU-test-{index}"
            row["index"] = index
        payload[field].append(row)
    assert len(getattr(parse_heartbeat(encode(payload)), field)) == 64
    payload[field].append(row)
    with pytest.raises(HeartbeatValidationError):
        parse_heartbeat(encode(payload))


def test_hash_ignores_json_formatting_and_equivalent_numeric_and_ip_notation():
    payload = heartbeat_payload()
    first = payload_digest(parse_heartbeat(encode(payload)))
    payload["cpu"]["utilization_percent"] = 0
    zero = payload_digest(parse_heartbeat(encode(payload)))
    payload["cpu"]["utilization_percent"] = 0.0
    assert payload_digest(parse_heartbeat(encode(payload))) == zero
    payload = heartbeat_payload()
    payload["ip_addresses"][1] = "2001:0db8:0:0:0:0:0:10"
    payload["collected_at"] = "2026-09-21T10:30:00+00:00"
    formatted = json.dumps(payload, sort_keys=True, indent=4).encode()
    assert payload_digest(parse_heartbeat(formatted)) == first
    payload["ip_addresses"].reverse()
    assert payload_digest(parse_heartbeat(encode(payload))) != first


@pytest.mark.parametrize(
    ("state", "reason", "reliable"),
    [
        ("GPU_MISSING", "no_gpu", True),
        ("NVIDIA_SMI_FAILED", "command_missing", False),
        ("NVIDIA_SMI_FAILED", "permission_denied", False),
        ("NVIDIA_SMI_FAILED", "timeout", False),
        ("NVIDIA_SMI_FAILED", "collector_stuck", False),
        ("NVIDIA_SMI_FAILED", "nonzero_exit", False),
        ("NVIDIA_SMI_FAILED", "malformed_output", False),
        ("NVIDIA_SMI_FAILED", "output_limit", False),
        ("DRIVER_ERROR", "driver_unavailable", False),
        ("UNKNOWN", "collector_error", False),
        ("UNKNOWN", "disabled", False),
    ],
)
def test_documented_empty_inventory_states_are_accepted(state, reason, reliable):
    payload = heartbeat_payload()
    payload["gpus"] = []
    payload["gpu_health"] = {"state": state, "reason_code": reason, "inventory_reliable": reliable}
    assert parse_heartbeat(encode(payload)).gpu_health.state == state


def test_unavailable_gpu_metrics_and_identity_are_preserved():
    payload = heartbeat_payload()
    payload["gpu_health"] = {
        "state": "UNKNOWN",
        "reason_code": "unsupported_metric",
        "inventory_reliable": True,
    }
    gpu = payload["gpus"][0]
    for field in [
        "uuid",
        "model",
        "driver_version",
        "utilization_percent",
        "temperature_celsius",
        "memory_total_bytes",
        "memory_used_bytes",
    ]:
        gpu[field] = None
    gpu["health"] = "UNKNOWN"
    gpu["reason_code"] = "unsupported_metric"
    assert parse_heartbeat(encode(payload)).gpus[0].uuid is None


@pytest.mark.parametrize(
    ("state", "reason", "reliable", "empty"),
    [
        ("OK", None, False, False),
        ("OK", None, True, True),
        ("GPU_MISSING", "no_gpu", False, True),
        ("GPU_MISSING", "no_gpu", True, False),
        ("NVIDIA_SMI_FAILED", "driver_unavailable", False, True),
        ("NVIDIA_SMI_FAILED", "timeout", True, True),
        ("NVIDIA_SMI_FAILED", "timeout", False, False),
        ("UNKNOWN", "unsupported_metric", False, False),
        ("UNKNOWN", "collector_error", True, True),
    ],
)
def test_contradictory_gpu_health_inventory_is_rejected(state, reason, reliable, empty):
    payload = heartbeat_payload()
    payload["gpu_health"] = {"state": state, "reason_code": reason, "inventory_reliable": reliable}
    if empty:
        payload["gpus"] = []
    with pytest.raises(HeartbeatValidationError):
        parse_heartbeat(encode(payload))
