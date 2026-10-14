"""Fixed updater protocol and archive checks without Linux service mutation."""

import hashlib
import json
import runpy
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / "scripts" / "agent-updater.py"


def _code():
    return runpy.run_path(str(UPDATER))


def _operation(**changes):
    result = {
        "operation_id": str(uuid4()),
        "action": "UPGRADE",
        "state": "REQUESTED",
        "target_version": "1.0.5",
        "target_wheel_sha256": "a" * 64,
        "archive_sha256": "b" * 64,
    }
    result.update(changes)
    return result


def test_updater_accepts_only_structured_pinned_operation_fields():
    code = _code()
    parse = code["operation"]
    failure = code["LocalFailure"]
    assert parse(_operation())["target_version"] == "1.0.5"
    with pytest.raises(failure):
        parse(_operation(command="systemctl restart other.service"))
    with pytest.raises(failure):
        parse(_operation(download_url="https://elsewhere.example/release.zip"))
    with pytest.raises(failure):
        parse(_operation(archive_sha256="0" * 63))
    with pytest.raises(failure):
        parse(_operation(action="ROLLBACK", archive_sha256="b" * 64))


def test_updater_rejects_archive_escape_and_symlink_before_extraction(tmp_path):
    code = _code()
    extract = code["extract_release"]
    failure = code["LocalFailure"]
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("skybeat-agent-1.0.5/../outside", "unsafe")
    with pytest.raises(failure):
        extract(archive, tmp_path / "dest", "1.0.5")

    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("skybeat-agent-1.0.5/README.txt", "first")
        source.writestr("skybeat-agent-1.0.5/README.txt", "second")
    with pytest.raises(failure):
        extract(archive, tmp_path / "dest", "1.0.5")
    assert not (tmp_path / "outside").exists()

    with zipfile.ZipFile(archive, "w") as source:
        entry = zipfile.ZipInfo("skybeat-agent-1.0.5/link")
        entry.external_attr = 0o120777 << 16
        source.writestr(entry, "target")
    with pytest.raises(failure):
        extract(archive, tmp_path / "dest", "1.0.5")


def test_interrupted_switch_accepts_only_after_local_health_and_keeps_candidate(
    tmp_path, monkeypatch
):
    code = _code()
    recover = code["recover_install"]
    state = tmp_path / "state"
    opt = tmp_path / "opt"
    state.mkdir()
    opt.mkdir()
    marker = state / "install.marker"
    marker.write_text("phase=SWITCHED\ntarget_sha256=" + "a" * 64 + "\n", encoding="ascii")
    (opt / "venv.candidate").mkdir()
    (opt / "venv.previous").mkdir()
    (opt / "VERSION").write_text("version=1.0.5\nsha256=" + "a" * 64 + "\n")
    (opt / "VERSION.candidate").write_text("version=1.0.4\nsha256=" + "b" * 64 + "\n")
    monkeypatch.setitem(recover.__globals__, "STATE", state)
    monkeypatch.setitem(recover.__globals__, "OPT", opt)
    monkeypatch.setitem(recover.__globals__, "INSTALL_MARKER", marker)
    monkeypatch.setitem(recover.__globals__, "local_health", lambda version: True)

    assert recover() == "succeeded"
    assert (opt / "venv.previous").is_dir()
    assert not (opt / "venv.candidate").exists()
    assert "version=1.0.4" in (opt / "VERSION.previous").read_text()
    assert not marker.exists()


def test_progress_reporting_outage_does_not_rollback_locally_healthy_upgrade(tmp_path, monkeypatch):
    code = _code()
    upgrade = code["upgrade"]
    state = tmp_path / "state"
    opt = tmp_path / "opt"
    state.mkdir()
    opt.mkdir()
    (opt / "VERSION").write_text("version=1.0.4\nsha256=" + "b" * 64 + "\n")
    archive = tmp_path / "approved.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr(
            "skybeat-agent-1.0.5/release-manifest.json",
            json.dumps({"package": {"filename": "skybeat_agent-1.0.5.whl", "sha256": "a" * 64}}),
        )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    reports = []

    def fake_run(*args, **kwargs):
        if "install-agent.sh" in args[1]:
            (opt / "VERSION").write_text("version=1.0.5\nsha256=" + "a" * 64 + "\n")
            (opt / "venv.previous").mkdir()
        return None

    monkeypatch.setitem(upgrade.__globals__, "STATE", state)
    monkeypatch.setitem(upgrade.__globals__, "OPT", opt)
    monkeypatch.setitem(
        upgrade.__globals__, "request", lambda *args, **kwargs: archive.read_bytes()
    )
    monkeypatch.setitem(upgrade.__globals__, "run", fake_run)
    monkeypatch.setitem(
        upgrade.__globals__, "report", lambda _values, _op, phase: reports.append(phase) or False
    )
    result = upgrade(
        {"SKYBEAT_SERVER_URL": "https://monitor.example.test"}, _operation(archive_sha256=digest)
    )

    assert result == ("SUCCEEDED", {"previous_wheel_sha256": "b" * 64, "rollback_available": True})
    assert reports == ["DOWNLOADING", "VERIFYING", "INSTALLING"]
    assert (opt / "VERSION").read_text().startswith("version=1.0.5")
