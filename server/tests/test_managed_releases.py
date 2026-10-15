"""Release registration keeps verified bytes and selection separate."""

import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest
from test_agent_release_service import (
    _archive,
    _refresh_release_integrity,
    _release_directory,
    _sha256,
)


def _stage(tmp_path: Path) -> tuple[Path, Path]:
    source = _release_directory(tmp_path / "source")
    _archive(source)
    root = tmp_path / "store"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    shutil.copytree(source, incoming / source.name)
    shutil.copy2(source.parent / f"{source.name}-linux.zip", incoming)
    return root, incoming / source.name


def _stage_next_version(root: Path, tmp_path: Path) -> Path:
    source = _release_directory(tmp_path / "next-source")
    candidate = source.with_name("skybeat-agent-1.0.1")
    source.rename(candidate)
    (candidate / "skybeat_agent-1.0.0-py3-none-any.whl").unlink()
    wheel = candidate / "skybeat_agent-1.0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "skybeat_agent-1.0.1.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: skybeat-agent\nVersion: 1.0.1\n",
        )
    manifest_path = candidate / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package"].update(version="1.0.1", filename=wheel.name, sha256=_sha256(wheel))
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    (candidate / "wheel.sha256").write_text(f"{_sha256(wheel)} *{wheel.name}\n", encoding="ascii")
    _refresh_release_integrity(candidate)
    release_archive = _archive(candidate)
    incoming = root / "incoming"
    shutil.copytree(candidate, incoming / candidate.name)
    shutil.copy2(release_archive, incoming / release_archive.name)
    return incoming / candidate.name


def test_import_verifies_and_copies_to_digest_named_storage(tmp_path: Path):
    from app.releases.managed import ReleaseStore

    root, candidate = _stage(tmp_path)
    store = ReleaseStore(root, "https://monitor.example.test")
    artifact = store.import_candidate(candidate.name)

    assert artifact.version == "1.0.0"
    assert artifact.archive_sha256 == _sha256(candidate.parent / f"{candidate.name}-linux.zip")
    assert artifact.bundle.samefile(
        root / "objects" / artifact.archive_sha256[:32] / candidate.name
    )
    assert store.validate(artifact.archive_sha256).archive_sha256 == artifact.archive_sha256


def test_import_handles_long_wheelhouse_path_on_windows(tmp_path: Path):
    from app.releases.managed import ReleaseStore

    source = _release_directory(tmp_path / "source")
    long_name = "dependency-" + "x" * 100 + ".whl"
    extra = source / "wheelhouse" / long_name
    extra.write_bytes(b"offline dependency")
    manifest_path = source / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["wheelhouse"].append({"filename": long_name, "sha256": _sha256(extra)})
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    _refresh_release_integrity(source)
    archive = _archive(source)
    root = tmp_path / "store"
    incoming = root / "incoming"
    incoming.mkdir(parents=True)
    shutil.copytree(source, incoming / source.name)
    shutil.copy2(archive, incoming / archive.name)

    stored = ReleaseStore(root.resolve(), "https://monitor.example.test").import_candidate(
        source.name
    )
    if os.name == "nt":
        assert (
            len(
                str(
                    root
                    / "objects"
                    / stored.archive_sha256[:32]
                    / source.name
                    / "wheelhouse"
                    / long_name
                )
            )
            > 260
        )
    assert (
        ReleaseStore(root.resolve(), "https://monitor.example.test")
        .validate(stored.archive_sha256)
        .archive_sha256
        == stored.archive_sha256
    )


@pytest.mark.parametrize(
    "name", ["../outside", "skybeat-agent-1.0.0/../other", "C:\\secrets", "other"]
)
def test_import_rejects_untrusted_names(tmp_path: Path, name: str):
    from app.releases.managed import ReleaseStore
    from app.releases.service import ReleaseUnavailable

    root, _ = _stage(tmp_path)
    with pytest.raises(ReleaseUnavailable):
        ReleaseStore(root, "https://monitor.example.test").import_candidate(name)


def test_import_rejects_candidate_symlink_and_changed_archive(tmp_path: Path):
    from app.releases.managed import ReleaseStore
    from app.releases.service import ReleaseUnavailable

    root, candidate = _stage(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"not a release")
    (candidate / "README.txt").unlink()
    try:
        (candidate / "README.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Local filesystem cannot create symlinks")
    with pytest.raises(ReleaseUnavailable):
        ReleaseStore(root, "https://monitor.example.test").import_candidate(candidate.name)

    (candidate / "README.txt").unlink()
    shutil.copy2(outside, candidate / "README.txt")
    with pytest.raises(ReleaseUnavailable):
        ReleaseStore(root, "https://monitor.example.test").import_candidate(candidate.name)


def test_registered_artifact_detects_mutation_and_missing_file(tmp_path: Path):
    from app.releases.managed import ReleaseStore
    from app.releases.service import ReleaseUnavailable

    root, candidate = _stage(tmp_path)
    store = ReleaseStore(root, "https://monitor.example.test")
    artifact = store.import_candidate(candidate.name)
    artifact.archive.write_bytes(b"changed")
    with pytest.raises(ReleaseUnavailable):
        store.validate(artifact.archive_sha256)
    artifact.archive.unlink()
    with pytest.raises(ReleaseUnavailable):
        store.validate(artifact.archive_sha256)


def test_import_rejects_directory_version_mismatch(tmp_path: Path):
    from app.releases.managed import ReleaseStore
    from app.releases.service import ReleaseUnavailable

    root, candidate = _stage(tmp_path)
    renamed = candidate.with_name("skybeat-agent-1.0.5")
    candidate.rename(renamed)
    _archive(renamed)
    with pytest.raises(ReleaseUnavailable):
        ReleaseStore(root, "https://monitor.example.test").import_candidate(renamed.name)


def test_release_management_has_dedicated_view_without_browser_paths():
    repository = Path(__file__).resolve().parents[2]
    template = (repository / "server/app/templates/dashboard.html").read_text(encoding="utf-8")
    script = (repository / "server/app/static/dashboard.js").read_text(encoding="utf-8")

    assert 'id="release-management"' in template
    assert 'id="release-register-name"' in template
    assert 'id="release-list"' in template
    assert '{% if active_view == "releases" %}' in template
    deployments = template.split('{% if active_view == "deployments" %}', 2)[-1].split(
        '{% if active_view == "releases" %}', 1
    )[0]
    assert 'id="release-register-form"' not in deployments
    assert 'href="/dashboard/releases"' in deployments
    assert 'fetch("/api/v1/agent-releases"' in script
    assert '"/api/v1/agent-releases/current"' in script
    assert "release-register-name" in script
    assert "filesystem path" not in template.lower()


def test_registry_models_have_one_selection_slot_and_digest_identity():
    from sqlalchemy import UniqueConstraint

    from app.models import AgentReleaseSelection, RegisteredAgentRelease

    assert RegisteredAgentRelease.__table__.primary_key.columns.keys() == ["archive_sha256"]
    assert AgentReleaseSelection.__table__.primary_key.columns.keys() == ["id"]
    assert AgentReleaseSelection.__table__.c.id.autoincrement is False
    assert any(
        isinstance(constraint, UniqueConstraint) and constraint.columns.keys() == ["version"]
        for constraint in RegisteredAgentRelease.__table__.constraints
    )


@pytest.mark.mysql
def test_release_selection_migration_creates_enforced_singleton_on_mysql(mysql_database):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with mysql_database.engine.connect() as connection:
        assert connection.scalar(text("SELECT VERSION()")).startswith("8.")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "93f20b4c17d6"
        assert (
            connection.scalar(
                text(
                    "SELECT EXTRA FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'agent_release_selection' "
                    "AND COLUMN_NAME = 'id'"
                )
            )
            == ""
        )
        assert (
            connection.scalar(
                text(
                    "SELECT ENFORCED FROM information_schema.TABLE_CONSTRAINTS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'agent_release_selection' "
                    "AND CONSTRAINT_NAME = 'ck_agent_release_selection_singleton'"
                )
            )
            == "YES"
        )
        assert (
            connection.scalar(text("SELECT COUNT(*) FROM agent_release_selection WHERE id = 1"))
            == 1
        )
        connection.rollback()

    with pytest.raises(DBAPIError) as failure:
        with mysql_database.transaction() as session:
            session.execute(text("INSERT INTO agent_release_selection (id) VALUES (2)"))
    assert failure.value.orig.args[0] == 3819
    with mysql_database.engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM agent_release_selection")) == 1


@pytest.mark.parametrize("role,expected", [("USER", 403), ("ADMIN", 201), ("OWNER", 201)])
def test_registration_route_requires_management_role_and_origin(role: str, expected: int):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.dashboard.service import DashboardUser
    from app.main import create_app
    from app.users.service import UserRole

    calls: list[tuple[str, str]] = []

    class Session:
        def authenticate_session(self, token: str) -> DashboardUser:
            return DashboardUser("google-user", "ops@example.test", None, 7, UserRole(role))

    class Releases:
        def register(self, name: str, actor: str) -> dict[str, object]:
            calls.append((name, actor))
            return {"version": "1.0.5", "archive_sha256": "a" * 64}

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()
    app.state.agent_release_service = Releases()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.post(
            "/api/v1/agent-releases",
            json={"name": "skybeat-agent-1.0.5"},
            headers={"Origin": "https://testserver"},
        )
    assert response.status_code == expected
    assert calls == ([] if role == "USER" else [("skybeat-agent-1.0.5", "ops@example.test")])


def test_registration_rejects_cross_origin_and_browser_path():
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.dashboard.service import DashboardUser
    from app.main import create_app
    from app.users.service import UserRole

    calls: list[str] = []

    class Session:
        def authenticate_session(self, token: str) -> DashboardUser:
            return DashboardUser("google-user", "ops@example.test", None, 7, UserRole.ADMIN)

    class Releases:
        def register(self, name: str, actor: str) -> dict[str, object]:
            calls.append(name)
            return {}

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()
    app.state.agent_release_service = Releases()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        wrong_origin = client.post(
            "/api/v1/agent-releases",
            json={"name": "skybeat-agent-1.0.5"},
            headers={"Origin": "https://other.example.test"},
        )
        browser_path = client.post(
            "/api/v1/agent-releases",
            json={"name": "../release-12jp1/skybeat-agent-1.0.5"},
            headers={"Origin": "https://testserver"},
        )
    assert wrong_origin.status_code == 403
    assert browser_path.status_code == 422
    assert calls == []


@pytest.mark.parametrize("role,expected", [("USER", 403), ("ADMIN", 200), ("OWNER", 200)])
@pytest.mark.parametrize("action", ["verify", "activate"])
def test_release_changes_require_management_role(role: str, expected: int, action: str):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.dashboard.service import DashboardUser
    from app.main import create_app
    from app.users.service import UserRole

    calls: list[tuple[str, str]] = []

    class Session:
        def authenticate_session(self, token: str) -> DashboardUser:
            return DashboardUser("google-user", "ops@example.test", None, 7, UserRole(role))

    class Releases:
        def verify(self, digest: str, actor: str) -> dict[str, object]:
            calls.append((digest, actor))
            return {"archive_sha256": digest}

        def activate(self, digest: str, actor: str) -> dict[str, object]:
            calls.append((digest, actor))
            return {"archive_sha256": digest}

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()
    app.state.agent_release_service = Releases()
    digest = "a" * 64
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.post(
            f"/api/v1/agent-releases/{digest}/{action}",
            headers={"Origin": "https://testserver"},
        )
    assert response.status_code == expected
    assert calls == ([] if role == "USER" else [(digest, "ops@example.test")])


def test_download_serves_imported_archive_to_admin_only(tmp_path: Path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.dashboard.service import DashboardUser
    from app.main import create_app
    from app.releases.managed import ReleaseStore
    from app.users.service import UserRole

    root, candidate = _stage(tmp_path)
    stored = ReleaseStore(root, "https://monitor.example.test").import_candidate(candidate.name)

    class Session:
        def authenticate_session(self, token: str) -> DashboardUser:
            role = UserRole.ADMIN if token == "admin" else UserRole.USER
            return DashboardUser("google-user", "ops@example.test", None, 7, role)

    class Releases:
        def archive(self) -> Path:
            return stored.archive

        def archive_by_digest(self, digest: str) -> Path:
            assert digest == stored.archive_sha256
            return stored.archive

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()
    app.state.agent_release_service = Releases()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "user")
        denied = client.get("/api/v1/agent-releases/current/download")
        denied_pinned = client.get(
            f"/api/v1/agent-releases/current/download?archive_sha256={stored.archive_sha256}"
        )
        client.cookies.set("__Host-skybeat_session", "admin")
        allowed = client.get("/api/v1/agent-releases/current/download")
        allowed_pinned = client.get(
            f"/api/v1/agent-releases/current/download?archive_sha256={stored.archive_sha256}"
        )
        invalid = client.get("/api/v1/agent-releases/current/download?archive_sha256=invalid")
    assert denied.status_code == 403
    assert denied_pinned.status_code == 403
    assert allowed.status_code == 200
    assert allowed_pinned.status_code == 200
    assert allowed_pinned.content == stored.archive.read_bytes()
    assert invalid.status_code == 422
    assert _sha256(stored.archive) == _sha256(candidate.parent / f"{candidate.name}-linux.zip")
    assert allowed.content == stored.archive.read_bytes()


@pytest.mark.mysql
def test_active_release_persists_across_service_instances_and_concurrent_activation(
    mysql_database, tmp_path: Path
):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import delete, func, select

    from app.models import AgentReleaseSelection, RegisteredAgentRelease
    from app.releases.registry import ManagedReleaseService

    root, candidate = _stage(tmp_path)
    next_candidate = _stage_next_version(root, tmp_path)
    with mysql_database.transaction() as session:
        selection = session.get(AgentReleaseSelection, 1)
        assert selection is not None
        selection.archive_sha256 = None
        session.execute(delete(RegisteredAgentRelease))
    try:
        service = ManagedReleaseService(mysql_database, root, "https://monitor.example.test")
        registered = service.register(candidate.name, "admin@example.test")
        digest = registered["archive_sha256"]
        assert isinstance(digest, str)
        next_registered = service.register(next_candidate.name, "admin@example.test")
        next_digest = next_registered["archive_sha256"]
        assert isinstance(next_digest, str) and next_digest != digest
        service.activate(digest, "owner@example.test")
        with ThreadPoolExecutor(max_workers=2) as pool:
            activated = list(
                pool.map(
                    lambda selected: service.activate(selected, "owner@example.test"),
                    (digest, next_digest),
                )
            )
        assert all(row["active"] is True for row in activated)
        restarted = ManagedReleaseService(mysql_database, root, "https://monitor.example.test")
        assert restarted.current().version in {"1.0.0", "1.0.1"}
        active_digest = next(row["archive_sha256"] for row in restarted.list() if row["active"])
        assert active_digest in {digest, next_digest}
        active_name = candidate.name if active_digest == digest else next_candidate.name
        assert restarted.archive().samefile(
            root / "objects" / active_digest[:32] / f"{active_name}-linux.zip"
        )
        assert restarted.archive_by_digest(digest).samefile(
            root / "objects" / digest[:32] / f"{candidate.name}-linux.zip"
        )
        assert restarted.archive_by_digest(next_digest).samefile(
            root / "objects" / next_digest[:32] / f"{next_candidate.name}-linux.zip"
        )
        assert sum(row["active"] is True for row in restarted.list()) == 1
        with mysql_database.transaction() as session:
            assert session.scalar(select(func.count()).select_from(AgentReleaseSelection)) == 1
    finally:
        with mysql_database.transaction() as session:
            selection = session.get(AgentReleaseSelection, 1)
            assert selection is not None
            selection.archive_sha256 = None
            session.execute(delete(RegisteredAgentRelease))


@pytest.mark.mysql
def test_api_tracks_explicit_activation_and_serves_pinned_verified_bytes(
    mysql_database, mysql_settings, tmp_path: Path
):
    from fastapi.testclient import TestClient
    from sqlalchemy import delete, select

    from app.dashboard.service import DashboardUser
    from app.main import create_app
    from app.models import AgentReleaseSelection, Device, RegisteredAgentRelease
    from app.releases.registry import ManagedReleaseService
    from app.users.service import UserRole

    root, candidate = _stage(tmp_path)
    next_candidate = _stage_next_version(root, tmp_path)
    with mysql_database.transaction() as session:
        selection = session.get(AgentReleaseSelection, 1)
        assert selection is not None
        selection.archive_sha256 = None
        session.execute(delete(RegisteredAgentRelease))
        identities = list(session.execute(select(Device.device_uuid).order_by(Device.id)).scalars())

    class Session:
        def authenticate_session(self, token: str) -> DashboardUser:
            return DashboardUser("google-user", "ops@example.test", None, 7, UserRole.ADMIN)

    service = ManagedReleaseService(mysql_database, root, "https://monitor.example.test")
    settings = mysql_settings.model_copy(
        update={"agent_release_store": root, "public_base_url": "https://testserver"}
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()
    app.state.agent_release_service = service
    try:
        with TestClient(app, base_url="https://testserver") as client:
            client.cookies.set("__Host-skybeat_session", "valid-browser-session")
            empty = client.get("/api/v1/agent-releases")
            assert empty.status_code == 200
            assert empty.json()["releases"] == []
            assert (
                empty.json()["storage_status"] == "Release store and staging directory: available."
            )
            assert client.get("/api/v1/agent-releases/current").status_code == 503

            first = service.register(candidate.name, "ops@example.test")
            digest = first["archive_sha256"]
            assert isinstance(digest, str)
            assert first["active"] is False
            assert client.get("/api/v1/agent-releases/current").status_code == 503
            service.activate(digest, "ops@example.test")
            current = client.get("/api/v1/agent-releases/current")
            assert current.status_code == 200
            assert current.json()["release"]["archive_sha256"] == digest
            assert current.json()["release"]["version"] == "1.0.0"
            original = client.get(
                f"/api/v1/agent-releases/current/download?archive_sha256={digest}"
            )
            assert original.status_code == 200
            assert (
                original.content == (candidate.parent / f"{candidate.name}-linux.zip").read_bytes()
            )
            assert (
                f'filename="{candidate.name}-linux.zip"' in original.headers["content-disposition"]
            )

            second = service.register(next_candidate.name, "ops@example.test")
            next_digest = second["archive_sha256"]
            assert isinstance(next_digest, str)
            assert (
                client.get("/api/v1/agent-releases/current").json()["release"]["version"] == "1.0.0"
            )
            service.activate(next_digest, "ops@example.test")
            assert (
                client.get("/api/v1/agent-releases/current").json()["release"]["version"] == "1.0.1"
            )
            pinned_old = client.get(
                f"/api/v1/agent-releases/current/download?archive_sha256={digest}"
            )
            assert pinned_old.status_code == 200
            assert pinned_old.content == original.content
            assert (
                client.get("/api/v1/agent-releases/current/download").content
                == (next_candidate.parent / f"{next_candidate.name}-linux.zip").read_bytes()
            )

            (root / "objects" / digest[:32] / f"{candidate.name}-linux.zip").write_bytes(
                b"corrupted"
            )
            assert (
                client.get(
                    f"/api/v1/agent-releases/current/download?archive_sha256={digest}"
                ).status_code
                == 503
            )
            assert client.get("/api/v1/agent-releases/current").status_code == 200
            (root / "objects" / next_digest[:32] / f"{next_candidate.name}-linux.zip").unlink()
            assert client.get("/api/v1/agent-releases/current").status_code == 503
            assert client.get("/api/v1/agent-releases/current/download").status_code == 503
        with mysql_database.transaction() as session:
            assert (
                list(session.execute(select(Device.device_uuid).order_by(Device.id)).scalars())
                == identities
            )
    finally:
        with mysql_database.transaction() as session:
            selection = session.get(AgentReleaseSelection, 1)
            assert selection is not None
            selection.archive_sha256 = None
            session.execute(delete(RegisteredAgentRelease))
