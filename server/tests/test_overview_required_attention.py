"""Current-state attention reasons must remain distinct from enrollment state."""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.dashboard.read import _required_attention_view


def _device(state, gpu, *, seen=True, monitoring=True):
    return SimpleNamespace(
        device_uuid="65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
        name="<script>device</script>",
        availability_state=state,
        gpu_effective_state=gpu,
        gpu_monitoring_enabled=monitoring,
        last_seen_at=datetime(2026, 10, 6, tzinfo=UTC) if seen else None,
    )


def test_required_attention_reasons_keep_communication_and_gpu_separate():
    project = SimpleNamespace(public_id="e3e70682-c209-4cac-a29f-6fbed82c07cd", name="Ops")
    offline_gpu = _device("OFFLINE", "DRIVER_ERROR")
    view = _required_attention_view(offline_gpu, project, True)
    assert view["communication_attention"] == "OFFLINE"
    assert view["gpu_attention"] is True
    assert view["name"] == "<script>device</script>"

    never_seen = _required_attention_view(_device("ONLINE", "UNKNOWN", seen=False), project, False)
    assert never_seen["state"] == "AWAITING_FIRST_HEARTBEAT"
    assert never_seen["communication_attention"] is None
    assert never_seen["gpu_attention"] is False

    unmonitored = _device("SUSPECT", "UNKNOWN", monitoring=False)
    view = _required_attention_view(unmonitored, project, False)
    assert view["communication_attention"] == "SUSPECT"
    assert view["gpu_attention"] is False
