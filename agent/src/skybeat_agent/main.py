"""Console entry point."""

import asyncio
import signal

from skybeat_agent.collectors.gpu import GPUCollector
from skybeat_agent.collectors.system import collect_system
from skybeat_agent.config import Config
from skybeat_agent.runtime import run
from skybeat_agent.transport import HeartbeatSender


def main() -> None:
    config = Config.from_env()
    stop = asyncio.Event()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stop.set)
    collector = GPUCollector(
        config.nvidia_smi_path,
        enabled=config.gpu_collection_enabled,
        timeout=config.nvidia_smi_timeout,
    )
    loop.run_until_complete(
        run(
            config,
            HeartbeatSender(config),
            system=lambda: collect_system(config.mountpoints),
            gpu=collector.collect,
            stop=stop,
        )
    )
