"""Transport policy checks shared by the release-bundled installer."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate-agent-server-url.py"


def _validate(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- invokes only the committed validation script.
        [sys.executable, str(VALIDATOR), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_https_agent_origin_is_accepted_without_a_local_override():
    result = _validate("--server", "https://monitor.example.test")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "origin",
    [
        "http://192.168.1.43:8000",
        "http://10.0.0.4",
        "http://127.0.0.1:8000",
    ],
)
def test_private_or_loopback_http_requires_explicit_local_override(origin: str):
    rejected = _validate("--server", origin)
    accepted = _validate("--server", origin, "--allow-insecure-local-server")

    assert rejected.returncode == 1
    assert accepted.returncode == 0, accepted.stderr


@pytest.mark.parametrize(
    "origin",
    [
        "http://monitor.example.test",
        "http://8.8.8.8",
        "http://user@192.168.1.43",
        "http://192.168.1.43/path",
        "https://monitor.example.test/path",
    ],
)
def test_agent_origin_validator_rejects_non_origin_or_public_http_even_with_override(origin: str):
    result = _validate("--server", origin, "--allow-insecure-local-server")

    assert result.returncode == 1
    assert "http://" not in result.stderr
