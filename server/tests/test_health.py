from datetime import UTC, datetime, timedelta

import pytest

from app.health.service import AvailabilityState, availability_state, monitoring_baseline


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [
        (74.999, AvailabilityState.ONLINE),
        (75, AvailabilityState.SUSPECT),
        (179.999, AvailabilityState.SUSPECT),
        (180, AvailabilityState.OFFLINE),
    ],
)
def test_availability_state_uses_exact_server_time_boundaries(age_seconds, expected):
    now = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)

    assert availability_state(now - timedelta(seconds=age_seconds), now) is expected


def test_monitoring_baseline_prefers_last_accepted_heartbeat():
    started = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
    seen = datetime(2026, 9, 23, 11, 0, tzinfo=UTC)

    assert monitoring_baseline(started, seen) == seen
    assert monitoring_baseline(started, None) == started
