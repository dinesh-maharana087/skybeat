import asyncio
import sys
import time

import pytest

from skybeat_agent.collectors.gpu import GPUCollector, parse_gpu_output
from skybeat_agent.collectors.process import BoundedProcess, ProcessResult

ROW = '0, GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee, "NVIDIA, Test", 35, 62, 24576, 6144, 570.10\n'


def test_gpu_csv_units_and_unavailable_metrics():
    result = parse_gpu_output(ROW.encode())
    assert result["gpu_health"] == {"state": "OK", "reason_code": None, "inventory_reliable": True}
    gpu = result["gpus"][0]
    assert gpu["model"] == "NVIDIA, Test"
    assert gpu["memory_total_bytes"] == 25769803776
    assert gpu["memory_used_bytes"] == 6442450944
    unknown = parse_gpu_output(ROW.replace("35, 62", "N/A, N/A").encode())
    assert unknown["gpus"][0]["utilization_percent"] is None
    assert unknown["gpu_health"]["state"] == "UNKNOWN"
    assert unknown["gpu_health"]["inventory_reliable"] is True


def test_gpu_memory_above_24_gib_is_supported_within_json_safe_limit():
    result = parse_gpu_output(ROW.replace("24576, 6144", "98304, 49152").encode())
    assert result["gpus"][0]["memory_total_bytes"] == 98304 * 1024 * 1024


def test_gpu_empty_and_reordered_inventory():
    assert parse_gpu_output(b"")["gpu_health"] == {
        "state": "GPU_MISSING",
        "reason_code": "no_gpu",
        "inventory_reliable": True,
    }
    other = ROW.replace("0, GPU-a", "1, GPU-b")
    result = parse_gpu_output((other + ROW).encode())
    assert [gpu["index"] for gpu in result["gpus"]] == [0, 1]


@pytest.mark.parametrize(
    "output,reason",
    [
        (b"bad,data", "malformed_output"),
        (ROW.replace("35,", "NaN,").encode(), "malformed_output"),
        (ROW.replace("35,", "101,").encode(), "malformed_output"),
        (ROW.replace("62,", "251,").encode(), "malformed_output"),
        (ROW.replace("6144,", "999999,").encode(), "malformed_output"),
        (ROW.replace("0, GPU-", "1024, GPU-").encode(), "malformed_output"),
        ((ROW + ROW).encode(), "malformed_output"),
        ((ROW + ROW.replace("0, GPU", "1, GPU")).encode(), "malformed_output"),
        (b"x" * 65537, "output_limit"),
        ((ROW * 65).encode(), "output_limit"),
        (b"\xff", "malformed_output"),
    ],
    ids=lambda value: (
        "oversized-output" if isinstance(value, bytes) and len(value) > 4096 else None
    ),
)
def test_bad_inventory_never_becomes_partial_healthy(output, reason):
    result = parse_gpu_output(output)
    assert result["gpus"] == []
    assert result["gpu_health"]["reason_code"] == reason
    assert result["gpu_health"]["inventory_reliable"] is False


def test_real_process_timeout_and_output_flood_are_bounded():
    async def exercise():
        process = BoundedProcess()
        started = time.monotonic()
        timeout = await process.run([sys.executable, "-c", "import time; time.sleep(30)"], 0.1)
        assert timeout.reason == "timeout"
        assert time.monotonic() - started < 3
        flood = await process.run([sys.executable, "-c", "print('x' * 1000000)"], 3)
        assert flood.reason == "output_limit"
        assert len(flood.output) <= 65536
        await process.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_output_limit_stops_a_process_that_remains_alive(stream):
    async def exercise():
        process = BoundedProcess()
        command = (
            "import os, sys, time; "
            "print(os.getpid(), flush=True); "
            f"getattr(sys, '{stream}').write('x' * 70000); "
            f"getattr(sys, '{stream}').flush(); "
            "time.sleep(30)"
        )
        started = time.monotonic()
        result = await process.run([sys.executable, "-c", command], timeout=3)

        assert result.reason == "output_limit"
        assert time.monotonic() - started < 1
        assert len(result.output) + len(result.error) <= 65536
        assert process._active is None

    asyncio.run(exercise())


def test_cancelling_collection_terminates_the_active_process():
    async def exercise():
        process = BoundedProcess()
        task = asyncio.create_task(
            process.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=10)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.05)
        assert process._active is None

    asyncio.run(exercise())


def test_disabled_and_missing_gpu_collector():
    async def exercise():
        disabled = GPUCollector("/missing/nvidia-smi", enabled=False)
        assert (await disabled.collect())["gpu_health"]["reason_code"] == "disabled"
        missing = GPUCollector("/missing/nvidia-smi")
        assert (await missing.collect())["gpu_health"]["reason_code"] == "command_missing"

    asyncio.run(exercise())


def test_known_driver_diagnostic_is_classified_without_matching_arbitrary_stderr():
    class FixedProcess:
        async def run(self, args, timeout):
            return ProcessResult(
                b"",
                b"Failed to initialize NVML: Driver/library version mismatch\n",
                1,
                "nonzero_exit",
            )

    async def exercise():
        result = await GPUCollector("/usr/bin/nvidia-smi", process=FixedProcess()).collect()
        assert result["gpu_health"] == {
            "state": "DRIVER_ERROR",
            "reason_code": "driver_unavailable",
            "inventory_reliable": False,
        }

    asyncio.run(exercise())
