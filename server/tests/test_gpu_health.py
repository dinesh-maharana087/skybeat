from datetime import UTC, datetime, timedelta

from app.gpu.service import GPUConfirmation, GPUEffectiveState, evaluate_gpu_observation


def test_two_consecutive_non_ok_observations_confirm_gpu_degradation():
    at = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    first = evaluate_gpu_observation(
        GPUConfirmation(GPUEffectiveState.OK, 0, 0, None),
        reported_state="NVIDIA_SMI_FAILED",
        inventory_reliable=False,
        gpus=(),
        expected_min_count=1,
        expected_uuids=(),
        observed_at=at,
    )
    second = evaluate_gpu_observation(
        first,
        reported_state="NVIDIA_SMI_FAILED",
        inventory_reliable=False,
        gpus=(),
        expected_min_count=1,
        expected_uuids=(),
        observed_at=at + timedelta(seconds=30),
    )

    assert first.failure_streak == 1
    assert first.event is None
    assert second.failure_streak == 2
    assert second.event == "GPU_DEGRADED"


def test_continuing_failures_do_not_repeat_degradation_and_two_ok_samples_recover():
    at = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    degraded = GPUConfirmation(GPUEffectiveState.DRIVER_ERROR, 2, 0, at, "GPU_DEGRADED")
    continuing = evaluate_gpu_observation(
        degraded,
        reported_state="NVIDIA_SMI_FAILED",
        inventory_reliable=False,
        gpus=(),
        expected_min_count=1,
        expected_uuids=(),
        observed_at=at + timedelta(seconds=30),
    )
    first_ok = evaluate_gpu_observation(
        continuing,
        reported_state="OK",
        inventory_reliable=True,
        gpus=({"uuid": "GPU-one"},),
        expected_min_count=1,
        expected_uuids=("GPU-one",),
        observed_at=at + timedelta(seconds=60),
    )
    recovered = evaluate_gpu_observation(
        first_ok,
        reported_state="OK",
        inventory_reliable=True,
        gpus=({"uuid": "GPU-one"},),
        expected_min_count=1,
        expected_uuids=("GPU-one",),
        observed_at=at + timedelta(seconds=75),
    )

    assert continuing.event is None
    assert first_ok.event is None
    assert recovered.event == "GPU_RECOVERED"
    assert recovered.state is GPUEffectiveState.OK


def test_gpu_confirmation_gap_and_cpu_only_policy_do_not_create_gpu_incident():
    at = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    prior = GPUConfirmation(GPUEffectiveState.OK, 1, 0, at)
    gapped = evaluate_gpu_observation(
        prior,
        reported_state="DRIVER_ERROR",
        inventory_reliable=False,
        gpus=(),
        expected_min_count=1,
        expected_uuids=(),
        observed_at=at + timedelta(seconds=76),
    )
    cpu_only = evaluate_gpu_observation(
        prior,
        reported_state="DRIVER_ERROR",
        inventory_reliable=False,
        gpus=(),
        expected_min_count=0,
        expected_uuids=(),
        observed_at=at,
        monitoring_enabled=False,
    )

    assert gapped.failure_streak == 1
    assert gapped.event is None
    assert cpu_only.state is GPUEffectiveState.NOT_MONITORED
    assert cpu_only.event is None


def test_exact_confirmation_gap_and_reordered_expected_inventory_are_valid():
    at = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    first = evaluate_gpu_observation(
        GPUConfirmation(GPUEffectiveState.OK, 0, 0, None),
        reported_state="OK",
        inventory_reliable=True,
        gpus=({"uuid": "GPU-two"}, {"uuid": "GPU-one"}),
        expected_min_count=2,
        expected_uuids=("GPU-one", "GPU-two"),
        observed_at=at,
    )
    second = evaluate_gpu_observation(
        GPUConfirmation(GPUEffectiveState.OK, 1, 0, at),
        reported_state="GPU_MISSING",
        inventory_reliable=True,
        gpus=({"uuid": "GPU-two"},),
        expected_min_count=2,
        expected_uuids=("GPU-one", "GPU-two"),
        observed_at=at + timedelta(seconds=75),
    )

    assert first.state is GPUEffectiveState.OK
    assert second.failure_streak == 2
    assert second.event == "GPU_DEGRADED"
