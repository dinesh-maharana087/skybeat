import asyncio
import logging

from skybeat_agent.config import Config
from skybeat_agent.logging import configure_logging
from skybeat_agent.telemetry import build_snapshot


def _config() -> Config:
    return Config.from_env(
        {
            "SKYBEAT_SERVER_URL": "https://monitor.example.test",
            "SKYBEAT_DEVICE_ID": "a4f82a6d-61c6-4c72-9a57-626e524571e4",
            "SKYBEAT_DEVICE_TOKEN": "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A",
        }
    )


def test_collector_exception_logs_safe_context_without_credential(caplog):
    config = _config()
    configure_logging("DEBUG")
    caplog.set_level(logging.DEBUG)

    async def system(_: float) -> dict[str, object]:
        raise RuntimeError(f"Authorization: Bearer {config.token}")

    async def gpu() -> dict[str, object]:
        return {
            "gpu_health": {
                "state": "GPU_MISSING",
                "reason_code": "no_gpu",
                "inventory_reliable": True,
            },
            "gpus": [],
        }

    snapshot = asyncio.run(build_snapshot(config, system=system, gpu=gpu))

    assert snapshot["hostname"] == "unknown"
    assert "collector_failed component=system category=system_collection_error" in caplog.text
    assert "RuntimeError" in caplog.text
    assert config.token not in caplog.text


def test_unexpected_exception_logging_cannot_bypass_redaction(caplog):
    config = _config()
    configure_logging("DEBUG")
    caplog.set_level(logging.DEBUG)
    logger = logging.getLogger("untrusted_dependency")

    try:
        raise RuntimeError(f"token={config.token} smtp_password=mail-secret")
    except RuntimeError:
        logger.exception("unexpected collector failure Authorization: Bearer %s", config.token)

    assert "unexpected collector failure" in caplog.text
    assert config.token not in caplog.text
    assert "mail-secret" not in caplog.text
