"""Local release diagnostics never select or activate an artifact."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.local_release_status import management_readiness, store_status
from app.releases.storage import inspect_storage


def test_release_store_diagnostic_requires_existing_absolute_root_and_staging(tmp_path: Path):
    assert "not configured" in store_status(None)
    assert "absolute" in store_status(Path("relative-store"))
    root = tmp_path / "store"
    assert "unavailable" in store_status(root)
    root.mkdir()
    assert "staging" in store_status(root)
    (root / "incoming").mkdir()
    assert store_status(root) == "Release store and staging directory: available and writable."
    assert management_readiness(inspect_storage(root), registry_compatible=True) == "ready"
    assert management_readiness(inspect_storage(root), registry_compatible=False) == "unavailable"


@pytest.mark.mysql
def test_release_diagnostic_reads_isolated_registry_without_exposing_url(
    mysql_database, tmp_path: Path
):
    environment = os.environ.copy()
    environment["SKYBEAT_DATABASE_URL"] = mysql_database.engine.url.render_as_string(
        hide_password=False
    )
    environment["SKYBEAT_ENV"] = "test"
    environment["SKYBEAT_AGENT_RELEASE_STORE"] = str(tmp_path / "missing-store")
    result = subprocess.run(  # noqa: S603 - fixed Python executable and local module
        [sys.executable, "-m", "app.local_release_status"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert "Release store: configured directory is unavailable." in result.stdout
    assert "Active installation release:" in result.stdout
    assert mysql_database.engine.url.password not in result.stdout + result.stderr
