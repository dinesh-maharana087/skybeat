"""Console entry point."""

import asyncio
import signal
from functools import partial

from skybeat_agent.collectors.gpu import GPUCollector
from skybeat_agent.collectors.system import collect_system, prime_cpu_sample
from skybeat_agent.config import Config
from skybeat_agent.logging import configure_logging
from skybeat_agent.runtime import run
from skybeat_agent.telemetry import bounded_system_collector
from skybeat_agent.transport import HeartbeatSender


def main() -> None:
    config = Config.from_env()
    configure_logging(config.log_level, secrets=(config.token,))
    prime_cpu_sample()
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
    try:
        loop.run_until_complete(
            run(
                config,
                HeartbeatSender(config),
                system=bounded_system_collector(partial(collect_system, config.mountpoints)),
                gpu=collector.collect,
                stop=stop,
            )
        )
    finally:
        loop.run_until_complete(collector.close())
        loop.close()
