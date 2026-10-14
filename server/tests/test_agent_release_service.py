"""Tests for the configured, immutable agent-release service."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _release_directory(tmp_path: Path, *, wheel_metadata_name: str = "skybeat-agent") -> Path:
    bundle = tmp_path / "skybeat-agent-1.0.0"
    wheelhouse = bundle / "wheelhouse"
    wheelhouse.mkdir(parents=True)
    wheel = bundle / "skybeat_agent-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "skybeat_agent-1.0.0.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: {wheel_metadata_name}\nVersion: 1.0.0\n",
        )
    dependency = wheelhouse / "psutil-1.0.0-py3-none-any.whl"
    dependency.write_bytes(b"offline dependency fixture")
    lock = bundle / "requirements.lock"
    lock.write_text("psutil==1.0.0 --hash=sha256:" + _sha256(dependency) + "\n", encoding="utf-8")
    artifacts = {
        "install-agent.sh": b"#!/usr/bin/env bash\n",
        "lib/skybeat_agent_install.sh": b"#!/usr/bin/env bash\n",
        "verify-agent-release.py": b"#!/usr/bin/env python3\n",
        "validate-agent-server-url.py": b"#!/usr/bin/env python3\n",
        "agent-updater.py": b"#!/usr/bin/env python3\n",
        "deployment/systemd/skybeat-agent.service": b"[Service]\n",
        "deployment/systemd/skybeat-updater.service": b"[Service]\n",
        "deployment/systemd/skybeat-updater.timer": b"[Timer]\n",
        "README.txt": b"SkyBeat agent deployment release.\n",
    }
    for filename, content in artifacts.items():
        path = bundle / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        "format": 2,
        "package": {
            "name": "skybeat-agent",
            "version": "1.0.0",
            "filename": wheel.name,
            "sha256": _sha256(wheel),
        },
        "requirements_lock": {"filename": lock.name, "sha256": _sha256(lock)},
        "wheelhouse": [{"filename": dependency.name, "sha256": _sha256(dependency)}],
        "installer_artifacts": [
            {"filename": filename, "sha256": _sha256(bundle / filename)}
            for filename in sorted(artifacts)
        ],
    }
    (bundle / "release-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    (bundle / "wheel.sha256").write_text(f"{_sha256(wheel)} *{wheel.name}\n", encoding="ascii")
    checksums = [(wheel.name, _sha256(wheel)), (lock.name, _sha256(lock))]
    checksums.extend((filename, _sha256(bundle / filename)) for filename in sorted(artifacts))
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{digest}  {filename}\n" for filename, digest in checksums), encoding="ascii"
    )
    return bundle


def _archive(bundle: Path) -> Path:
    archive_path = bundle.parent / f"{bundle.name}-linux.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                archive.write(path, Path(bundle.name) / path.relative_to(bundle))
    return archive_path


def _refresh_release_integrity(bundle: Path) -> None:
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = [record["filename"] for record in manifest["installer_artifacts"]]
    manifest["installer_artifacts"] = [
        {"filename": filename, "sha256": _sha256(bundle / filename)}
        for filename in sorted(artifacts)
    ]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    checksums = [
        (manifest["package"]["filename"], _sha256(bundle / manifest["package"]["filename"])),
        (
            manifest["requirements_lock"]["filename"],
            _sha256(bundle / manifest["requirements_lock"]["filename"]),
        ),
        *[(filename, _sha256(bundle / filename)) for filename in sorted(artifacts)],
    ]
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{digest}  {filename}\n" for filename, digest in checksums), encoding="ascii"
    )


def test_release_service_fails_safely_when_no_release_directory_is_configured():
    from app.releases.service import AgentReleaseService, ReleaseUnavailable

    with pytest.raises(ReleaseUnavailable):
        AgentReleaseService(None, "https://monitor.example.test").current()


def test_release_service_returns_exact_validated_manifest_metadata_and_archive(tmp_path):
    from app.releases.service import AgentReleaseService

    bundle = _release_directory(tmp_path)
    archive = _archive(bundle)

    service = AgentReleaseService(bundle.resolve(), "https://monitor.example.test")

    metadata = service.current()

    assert metadata.wheel_filename == "skybeat_agent-1.0.0-py3-none-any.whl"
    assert metadata.wheel_sha256 == _sha256(bundle / metadata.wheel_filename)
    assert metadata.archive_filename == archive.name
    assert metadata.archive_root == bundle.name
    assert service.archive() == archive


def test_release_service_rejects_an_archive_that_does_not_match_the_validated_directory(tmp_path):
    from app.releases.service import AgentReleaseService, ReleaseUnavailable

    bundle = _release_directory(tmp_path)
    archive = _archive(bundle)
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr(f"{bundle.name}/unexpected.txt", "not an approved artifact")

    with pytest.raises(ReleaseUnavailable):
        AgentReleaseService(bundle.resolve(), "https://monitor.example.test").archive()


def test_release_service_rejects_checksum_files_that_disagree_with_the_manifest(tmp_path):
    from app.releases.service import AgentReleaseService, ReleaseUnavailable

    bundle = _release_directory(tmp_path)
    _archive(bundle)
    (bundle / "wheel.sha256").write_text(
        "0" * 64 + " *skybeat_agent-1.0.0-py3-none-any.whl\n", encoding="ascii"
    )

    with pytest.raises(ReleaseUnavailable):
        AgentReleaseService(bundle.resolve(), "https://monitor.example.test").current()


def test_release_service_accepts_the_builder_sha256sum_text_record(tmp_path):
    from app.releases.service import AgentReleaseService

    bundle = _release_directory(tmp_path)
    manifest = json.loads((bundle / "release-manifest.json").read_text(encoding="utf-8"))
    wheel = manifest["package"]
    (bundle / "wheel.sha256").write_text(
        f"{wheel['sha256']}  {wheel['filename']}\n", encoding="ascii"
    )

    assert AgentReleaseService(bundle.resolve(), "https://monitor.example.test").current()


def test_release_service_rejects_a_server_wheel_renamed_to_look_like_an_agent_wheel(tmp_path):
    from app.releases.service import AgentReleaseService, ReleaseUnavailable

    bundle = _release_directory(tmp_path, wheel_metadata_name="skybeat-server")

    with pytest.raises(ReleaseUnavailable):
        AgentReleaseService(bundle.resolve(), "https://monitor.example.test").current()


def test_release_service_rejects_a_declared_server_wheel_in_the_wheelhouse(tmp_path):
    from app.releases.service import AgentReleaseService, ReleaseUnavailable

    bundle = _release_directory(tmp_path)
    server_wheel = bundle / "wheelhouse" / "skybeat_server-1.0.0-py3-none-any.whl"
    server_wheel.write_bytes(b"server wheel")
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["wheelhouse"].append({"filename": server_wheel.name, "sha256": _sha256(server_wheel)})
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseUnavailable):
        AgentReleaseService(bundle.resolve(), "https://monitor.example.test").current()


def test_release_service_rejects_a_secret_like_value_in_a_generic_release_artifact(tmp_path):
    from app.releases.service import AgentReleaseService, ReleaseUnavailable

    bundle = _release_directory(tmp_path)
    (bundle / "README.txt").write_text(
        "Enrollment credential: sbe1.00000000-0000-0000-0000-000000000000." + "a" * 43,
        encoding="utf-8",
    )
    _refresh_release_integrity(bundle)

    with pytest.raises(ReleaseUnavailable):
        AgentReleaseService(bundle.resolve(), "https://monitor.example.test").current()
