from dataclasses import FrozenInstanceError

import pytest

from skybeat_agent.config import Config, ConfigurationError

DEVICE = "a4f82a6d-61c6-4c72-9a57-626e524571e4"
TOKEN = "sb1.8cf5c647-70a0-4559-a4da-1a39dd66c119." + "a" * 42 + "A"


def environment(**overrides):
    return {
        "SKYBEAT_SERVER_URL": "https://monitor.example.test",
        "SKYBEAT_DEVICE_ID": DEVICE,
        "SKYBEAT_DEVICE_TOKEN": TOKEN,
        **overrides,
    }


def test_config_defaults_are_safe_and_secrets_are_hidden():
    config = Config.from_env(environment())
    assert config.server_url == "https://monitor.example.test"
    assert config.interval == 30
    assert config.request_timeout == 10
    assert config.max_attempts == 3
    assert config.mountpoints == ("/",)
    assert TOKEN not in repr(config)
    with pytest.raises(FrozenInstanceError):
        config.token = "replacement"


@pytest.mark.parametrize(
    "key,value",
    [
        ("SKYBEAT_SERVER_URL", "http://monitor.example.test"),
        ("SKYBEAT_SERVER_URL", "https://user:password@monitor.example.test"),
        ("SKYBEAT_SERVER_URL", "https://monitor.example.test/path"),
        ("SKYBEAT_SERVER_URL", "https://monitor.example.test?token=secret"),
        ("SKYBEAT_DEVICE_ID", "bad"),
        ("SKYBEAT_DEVICE_TOKEN", "secret\nheader"),
        ("SKYBEAT_HEARTBEAT_INTERVAL_SECONDS", "0"),
        ("SKYBEAT_REQUEST_TIMEOUT_SECONDS", "nan"),
        ("SKYBEAT_REQUEST_TIMEOUT_SECONDS", "31"),
        ("SKYBEAT_CONNECT_TIMEOUT_SECONDS", "0"),
        ("SKYBEAT_MAX_SEND_ATTEMPTS", "4"),
        ("SKYBEAT_GPU_COLLECTION_ENABLED", "perhaps"),
        ("SKYBEAT_NVIDIA_SMI_PATH", "nvidia-smi"),
        ("SKYBEAT_NVIDIA_SMI_TIMEOUT_SECONDS", "11"),
        ("SKYBEAT_DISK_MOUNTPOINTS", "/,/"),
        ("SKYBEAT_DISK_MOUNTPOINTS", "relative"),
        ("SKYBEAT_DISK_MOUNTPOINTS", ",".join(f"/disk{i}" for i in range(65))),
        ("SKYBEAT_LOG_LEVEL", "everything"),
    ],
)
def test_invalid_configuration_is_rejected_without_echoing_values(key, value):
    with pytest.raises(ConfigurationError) as error:
        Config.from_env(environment(**{key: value}))
    assert value not in str(error.value)


@pytest.mark.parametrize("key", ["SKYBEAT_SERVER_URL", "SKYBEAT_DEVICE_ID", "SKYBEAT_DEVICE_TOKEN"])
def test_required_configuration(key):
    env = environment()
    del env[key]
    with pytest.raises(ConfigurationError):
        Config.from_env(env)
