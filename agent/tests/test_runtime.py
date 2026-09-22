import asyncio
import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from time import monotonic

from skybeat_agent.config import Config
from skybeat_agent.runtime import run


async def _test_system(_: float) -> dict[str, object]:
    return {
        "hostname": "test",
        "ip_addresses": [],
        "os": {"name": None, "version": None, "kernel": None, "architecture": None},
        "uptime_seconds": None,
        "cpu": {"utilization_percent": None},
        "memory": {
            "total_bytes": None,
            "used_bytes": None,
            "available_bytes": None,
            "utilization_percent": None,
        },
        "disks": [],
    }


def test_agent_process_exits_promptly_when_system_collector_is_permanently_stuck():
    source_root = Path(__file__).parents[1] / "src"
    script = """
import asyncio
import os
from pathlib import Path

from skybeat_agent.config import Config
from skybeat_agent.collectors.system import BoundedSystemCollector
from skybeat_agent.runtime import run
from support_stuck_collector import collect_forever

config = Config.from_env({
    "SKYBEAT_SERVER_URL": "https://monitor.example.test",
    "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
    "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
})

async def exercise():
    stop = asyncio.Event()

    async def gpu():
        return {
            "gpu_health": {
                "state": "GPU_MISSING",
                "reason_code": "no_gpu",
                "inventory_reliable": True,
            },
            "gpus": [],
        }

    class Sender:
        async def send(self, snapshot):
            raise AssertionError("send must not start")

    collector = BoundedSystemCollector(collect_forever)
    task = asyncio.create_task(
        run(
            config,
            Sender(),
            system=collector.collect,
            gpu=gpu,
            stop=stop,
            jitter=lambda _, __: 0,
        )
    )
    while not Path(os.environ["SKYBEAT_TEST_STUCK_MARKER"]).is_file():
        await asyncio.sleep(0.01)
    stop.set()
    await task

if __name__ == "__main__":
    asyncio.run(exercise())
"""
    with tempfile.TemporaryDirectory() as temporary_directory:
        marker = Path(temporary_directory) / "collector-entered"
        environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(source_root), str(Path(__file__).parent))),
            "SKYBEAT_TEST_STUCK_MARKER": str(marker),
        }
        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise AssertionError(
                "agent did not exit after a permanently stuck system collector"
            ) from error

    assert result.returncode == 0, result.stderr


def test_runtime_stops_after_current_send_without_scheduling_another_snapshot():
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )

    async def exercise():
        stop = asyncio.Event()
        sent = []

        class Sender:
            async def send(self, snapshot):
                sent.append(snapshot)
                stop.set()
                return True

        async def gpu():
            return {
                "gpu_health": {
                    "state": "GPU_MISSING",
                    "reason_code": "no_gpu",
                    "inventory_reliable": True,
                },
                "gpus": [],
            }

        await run(
            replace(config, interval=1),
            Sender(),
            system=_test_system,
            gpu=gpu,
            stop=stop,
            jitter=lambda _, __: 0,
        )
        return sent

    assert len(asyncio.run(exercise())) == 1


def test_runtime_cancels_inflight_collection_when_stop_is_set():
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )

    async def exercise():
        stop = asyncio.Event()
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class Sender:
            async def send(self, snapshot):
                raise AssertionError("send must not start after shutdown")

        async def gpu():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(
            run(
                replace(config, nvidia_smi_timeout=10),
                Sender(),
                system=_test_system,
                gpu=gpu,
                stop=stop,
                jitter=lambda _, __: 0,
            )
        )
        await started.wait()
        began = monotonic()
        stop.set()
        await task
        assert monotonic() - began < 1
        assert cancelled.is_set()

    asyncio.run(exercise())


def test_runtime_uses_bounded_startup_jitter_before_collecting():
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )

    async def exercise():
        stop = asyncio.Event()
        ranges = []

        class Sender:
            async def send(self, snapshot):
                stop.set()
                return True

        async def gpu():
            return {
                "gpu_health": {
                    "state": "GPU_MISSING",
                    "reason_code": "no_gpu",
                    "inventory_reliable": True,
                },
                "gpus": [],
            }

        await run(
            config,
            Sender(),
            system=_test_system,
            gpu=gpu,
            stop=stop,
            jitter=lambda lower, upper: ranges.append((lower, upper)) or 0,
        )
        return ranges

    assert asyncio.run(exercise()) == [(0.0, 3.0)]


def test_runtime_cancels_inflight_send_when_stop_is_set():
    config = Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )

    async def exercise():
        stop = asyncio.Event()
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class Sender:
            async def send(self, snapshot):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        async def gpu():
            return {
                "gpu_health": {
                    "state": "GPU_MISSING",
                    "reason_code": "no_gpu",
                    "inventory_reliable": True,
                },
                "gpus": [],
            }

        task = asyncio.create_task(
            run(
                config,
                Sender(),
                system=_test_system,
                gpu=gpu,
                stop=stop,
                jitter=lambda _, __: 0,
            )
        )
        await started.wait()
        stop.set()
        await task
        assert cancelled.is_set()

    asyncio.run(exercise())
