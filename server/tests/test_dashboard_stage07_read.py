from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.dashboard import read

DEVICE_UUID = "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0"
ROOT = Path(__file__).resolve().parents[2]


def _sample(
    offset: int,
    *,
    cpu: float | None,
    memory: float | None,
    gpus: list[dict[str, object]],
) -> SimpleNamespace:
    return SimpleNamespace(
        received_at=datetime(2026, 9, 23, 10, 0, tzinfo=UTC) + timedelta(minutes=offset),
        payload={
            "cpu": {"utilization_percent": cpu},
            "memory": {"utilization_percent": memory},
            "gpus": gpus,
        },
    )


def test_device_cursor_round_trips_and_rejects_invalid_input():
    cursor = read.DeviceCursor("Ops", "Node", DEVICE_UUID)

    assert read.decode_device_cursor(read.encode_device_cursor(cursor)) == cursor

    for value in ("not-a-cursor", "a" * 513, "eyJ2IjoyfQ"):
        with pytest.raises(ValueError, match="Cursor is invalid"):
            read.decode_device_cursor(value)


def test_history_projection_prefers_gpu_uuid_and_preserves_null_metrics():
    projection = read.downsample_history(
        [
            _sample(
                0,
                cpu=None,
                memory=31.0,
                gpus=[
                    {
                        "uuid": "GPU-a",
                        "index": 3,
                        "utilization_percent": 41.0,
                        "temperature_celsius": None,
                    }
                ],
            ),
            _sample(
                1,
                cpu=42.0,
                memory=None,
                gpus=[
                    {
                        "uuid": None,
                        "index": 3,
                        "utilization_percent": None,
                        "temperature_celsius": 63.0,
                    }
                ],
            ),
        ]
    )

    assert projection["cpu_utilization"][0]["value"] is None
    assert projection["memory_utilization"][1]["value"] is None
    assert projection["gpu_series"] == [
        {
            "series_id": "index:3",
            "identity": {"kind": "index", "value": 3},
            "utilization": [{"received_at": "2026-09-23T10:01:00.000000Z", "value": None}],
            "temperature": [{"received_at": "2026-09-23T10:01:00.000000Z", "value": 63.0}],
        },
        {
            "series_id": "uuid:GPU-a",
            "identity": {"kind": "uuid", "value": "GPU-a"},
            "utilization": [{"received_at": "2026-09-23T10:00:00.000000Z", "value": 41.0}],
            "temperature": [{"received_at": "2026-09-23T10:00:00.000000Z", "value": None}],
        },
    ]
    assert projection["series_truncated"] is False


def test_device_list_rejects_noncanonical_gpu_state_before_database_access():
    service = read.DashboardReadService(object())

    with pytest.raises(ValueError, match="GPU state is invalid"):
        service.list_devices(gpu_state="NOT_A_GPU_STATE")


def test_incident_projection_exposes_lifecycle_without_notification_destinations():
    item = read._incident_view(
        SimpleNamespace(
            incident_uuid="b3c25c96-b14e-44d2-8fec-3db958b39c98",
            incident_type="GPU",
            current_reason="driver_unavailable",
            opened_at=datetime(2026, 9, 23, 10, 0, tzinfo=UTC),
            closed_at=None,
            close_reason=None,
        ),
        SimpleNamespace(device_uuid=DEVICE_UUID, name="Node"),
        SimpleNamespace(name="Ops"),
    )

    assert item == {
        "incident_id": "b3c25c96-b14e-44d2-8fec-3db958b39c98",
        "device_id": DEVICE_UUID,
        "device_name": "Node",
        "project_name": "Ops",
        "type": "GPU",
        "reason": "driver_unavailable",
        "opened_at": "2026-09-23T10:00:00.000000Z",
        "closed_at": None,
        "status": "ACTIVE",
        "resolution": None,
    }
    assert "destination" not in repr(item).lower()


def test_history_rejects_an_unsupported_range_before_database_access():
    service = read.DashboardReadService(object())

    with pytest.raises(ValueError, match="Range is invalid"):
        service.device_history(DEVICE_UUID, "8h")


def test_history_downsampling_and_raw_cap_keep_the_most_recent_bounded_window(monkeypatch):
    now = datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
    samples = [
        _sample(offset, cpu=float(offset), memory=float(offset), gpus=[])
        for offset in range(read.HISTORY_RAW_CAP + 1)
    ]

    class ScalarResult:
        def all(self):
            return list(reversed(samples))

    class Session:
        def scalar(self, statement):
            return 7

        def scalars(self, statement):
            return ScalarResult()

    class Database:
        @contextmanager
        def transaction(self):
            yield Session()

    monkeypatch.setattr(read, "database_utc", lambda session: now)

    history = read.DashboardReadService(Database()).device_history(DEVICE_UUID, "7d")

    assert history["truncated"] is True
    assert history["raw_sample_count"] == read.HISTORY_RAW_CAP
    assert len(history["cpu_utilization"]) == read.HISTORY_POINT_CAP
    assert history["cpu_utilization"][-1]["value"] == float(read.HISTORY_RAW_CAP)


def test_history_bounds_distinct_gpu_series_to_the_most_recent_canonical_identities():
    samples = [
        _sample(
            offset,
            cpu=10.0,
            memory=20.0,
            gpus=[
                {
                    "uuid": f"GPU-{offset}",
                    "index": 0,
                    "utilization_percent": 30.0,
                    "temperature_celsius": 50.0,
                }
            ],
        )
        for offset in range(read.HISTORY_GPU_SERIES_CAP + 1)
    ]

    projection = read.downsample_history(samples)

    assert projection["series_truncated"] is True
    assert len(projection["gpu_series"]) == read.HISTORY_GPU_SERIES_CAP
    assert f"uuid:GPU-{read.HISTORY_GPU_SERIES_CAP}" in {
        item["series_id"] for item in projection["gpu_series"]
    }
    assert "uuid:GPU-0" not in {item["series_id"] for item in projection["gpu_series"]}


def test_api_spec_documents_bounded_authenticated_stage07_read_endpoints():
    api_spec = (ROOT / "docs" / "API_SPEC.md").read_text(encoding="utf-8")

    assert "GET /api/v1/dashboard/overview" in api_spec
    assert "GET /api/v1/incidents" in api_spec
    assert "range=1h|6h|24h|7d" in api_spec
    assert "maximum page size of 100" in api_spec
