"""Portable release storage policy and safe initialization."""

from pathlib import Path

import pytest

from app.config import Settings
from app.releases.service import ReleaseUnavailable
from app.releases.storage import inspect_storage, prepare_storage, resolve_storage_root


def test_windows_default_uses_persistent_local_app_data(tmp_path: Path):
    root = resolve_storage_root(
        None, "development", platform="nt", variables={"LOCALAPPDATA": str(tmp_path / "AppData")}
    )
    assert root == (tmp_path / "AppData" / "SkyBeat" / "agent-releases").resolve()


def test_linux_default_uses_xdg_data_home(tmp_path: Path):
    root = resolve_storage_root(
        None,
        "development",
        platform="posix",
        variables={"XDG_DATA_HOME": str(tmp_path / "xdg")},
        user_home=tmp_path,
    )
    assert root == (tmp_path / "xdg" / "skybeat" / "agent-releases").resolve()


def test_linux_relative_xdg_value_falls_back_to_home(tmp_path: Path):
    root = resolve_storage_root(
        None,
        "development",
        platform="posix",
        variables={"XDG_DATA_HOME": "relative-data"},
        user_home=tmp_path,
    )
    assert root == (tmp_path / ".local" / "share" / "skybeat" / "agent-releases").resolve()


def test_explicit_root_precedes_platform_default(tmp_path: Path):
    explicit = tmp_path / "chosen"
    assert (
        resolve_storage_root(
            explicit, "development", platform="nt", variables={"LOCALAPPDATA": "C:\\other"}
        )
        == explicit.resolve()
    )


def test_production_requires_explicit_root():
    with pytest.raises(ReleaseUnavailable, match="explicit durable"):
        resolve_storage_root(None, "production")


def test_relative_and_linked_roots_are_rejected(tmp_path: Path):
    with pytest.raises(ReleaseUnavailable, match="absolute"):
        resolve_storage_root(Path("relative-store"), "development")
    with pytest.raises(ReleaseUnavailable, match="traversal"):
        resolve_storage_root(tmp_path / "nested" / ".." / "store", "development")
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Local filesystem cannot create symlinks")
    with pytest.raises(ReleaseUnavailable, match="linked"):
        resolve_storage_root(linked / "store", "development")


def test_default_development_store_initializes_only_dedicated_root(tmp_path: Path):
    root = tmp_path / "data" / "skybeat" / "agent-releases"
    prepare_storage(root, development_default=True)
    assert (root / "incoming").is_dir()
    assert inspect_storage(root).writable
    assert inspect_storage(root).staging_ready
    marker = root / "incoming" / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    prepare_storage(root, development_default=True)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_explicit_store_is_never_created(tmp_path: Path):
    root = tmp_path / "explicit"
    prepare_storage(root, development_default=False)
    assert not root.exists()
    assert not inspect_storage(root).available


def test_file_and_unwritable_store_are_unavailable(tmp_path: Path, monkeypatch):
    root = tmp_path / "store"
    root.write_text("file", encoding="utf-8")
    assert not inspect_storage(root).available
    root.unlink()
    (root / "incoming").mkdir(parents=True)
    monkeypatch.setattr("app.releases.storage.os.access", lambda *_: False)
    assert not inspect_storage(root).writable


def test_settings_exposes_one_resolved_root_for_release_consumers(tmp_path: Path):
    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test",
        agent_release_store=tmp_path / "chosen",
    )
    assert settings.release_store_root == (tmp_path / "chosen").resolve()


def test_production_settings_reject_missing_release_store():
    with pytest.raises(ValueError, match="explicit durable"):
        Settings(
            env="production",
            database_url="mysql+pymysql://runtime:example@mysql/skybeat",
            public_base_url="https://monitor.example.test",
            allowed_hosts=["monitor.example.test"],
            google_client_id="skybeat-client",
            google_client_secret="google-client-secret",
            session_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            allowed_emails=["ops@example.test"],
        )


def test_compose_requires_operator_selected_persistent_host_directory():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "${RELEASE_STORE_HOST_DIR:?" in compose
    assert ":/var/lib/skybeat/agent-releases:rw" in compose
