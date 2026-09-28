"""Release bundle contract tests; no network or production artifacts are used."""

import hashlib
import json
import runpy
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "verify-agent-release.py"
BUILDER = ROOT / "scripts" / "build-agent-release.sh"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path, *, windows_only_dependency: bool = False) -> Path:
    bundle = tmp_path / "skybeat-agent-1.0.0"
    wheelhouse = bundle / "wheelhouse"
    wheelhouse.mkdir(parents=True)
    wheel = bundle / "skybeat_agent-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "skybeat_agent-1.0.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: skybeat-agent\nVersion: 1.0.0\n",
        )
    dependency = wheelhouse / "psutil-1.0.0-py3-none-any.whl"
    dependency.write_bytes(b"offline dependency fixture")
    lock = bundle / "requirements.lock"
    lock_contents = "psutil==1.0.0 --hash=sha256:" + _sha256(dependency) + "\n"
    if windows_only_dependency:
        lock_contents += (
            'colorama==0.4.6 ; sys_platform == "win32" \\\n    --hash=sha256:' + "a" * 64 + "\n"
        )
    lock.write_text(lock_contents, encoding="utf-8")
    manifest = {
        "format": 1,
        "package": {
            "name": "skybeat-agent",
            "version": "1.0.0",
            "filename": wheel.name,
            "sha256": _sha256(wheel),
        },
        "requirements_lock": {"filename": lock.name, "sha256": _sha256(lock)},
        "wheelhouse": [
            {"filename": dependency.name, "sha256": _sha256(dependency)},
        ],
    }
    (bundle / "release-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    return bundle


def _deployment_bundle(tmp_path: Path) -> Path:
    bundle = _bundle(tmp_path)
    artifacts = {
        "install-agent.sh": b"#!/usr/bin/env bash\n",
        "lib/skybeat_agent_install.sh": b"#!/usr/bin/env bash\n",
        "verify-agent-release.py": b"#!/usr/bin/env python3\n",
        "validate-agent-server-url.py": b"#!/usr/bin/env python3\n",
        "deployment/systemd/skybeat-agent.service": b"[Service]\n",
        "README.txt": b"SkyBeat agent deployment release.\n",
    }
    for filename, content in artifacts.items():
        path = bundle / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["format"] = 2
    manifest["installer_artifacts"] = [
        {"filename": filename, "sha256": _sha256(bundle / filename)}
        for filename in sorted(artifacts)
    ]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    wheel = bundle / manifest["package"]["filename"]
    (bundle / "wheel.sha256").write_text(f"{_sha256(wheel)} *{wheel.name}\n", encoding="ascii")
    checksums = [
        (wheel.name, _sha256(wheel)),
        ("requirements.lock", _sha256(bundle / "requirements.lock")),
        *[(filename, _sha256(bundle / filename)) for filename in sorted(artifacts)],
    ]
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{digest}  {filename}\n" for filename, digest in checksums), encoding="ascii"
    )
    return bundle


def _refresh_deployment_integrity(bundle: Path) -> None:
    """Re-sign a fixture after a deliberate, non-secret-content mutation."""
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = [record["filename"] for record in manifest["installer_artifacts"]]
    manifest["installer_artifacts"] = [
        {"filename": filename, "sha256": _sha256(bundle / filename)}
        for filename in sorted(artifacts)
    ]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    wheel = manifest["package"]
    checksums = [
        (wheel["filename"], _sha256(bundle / wheel["filename"])),
        ("requirements.lock", _sha256(bundle / "requirements.lock")),
        *[(filename, _sha256(bundle / filename)) for filename in sorted(artifacts)],
    ]
    (bundle / "SHA256SUMS").write_text(
        "".join(f"{digest}  {filename}\n" for filename, digest in checksums), encoding="ascii"
    )


def _verify(bundle: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - invokes only the committed local verifier.
        [sys.executable, str(VERIFIER), "--bundle", str(bundle)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_verifier_accepts_a_complete_hash_locked_offline_bundle(tmp_path):
    result = _verify(_bundle(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout == "SkyBeat agent release bundle is valid.\n"


def test_release_verifier_accepts_a_self_contained_agent_deployment_bundle(tmp_path):
    result = _verify(_deployment_bundle(tmp_path))

    assert result.returncode == 0, result.stderr


def test_release_verifier_ignores_windows_only_locked_dependencies_for_linux_bundle(tmp_path):
    result = _verify(_bundle(tmp_path, windows_only_dependency=True))

    assert result.returncode == 0, result.stderr


def test_release_verifier_accepts_the_builder_sha256sum_text_record(tmp_path):
    bundle = _deployment_bundle(tmp_path)
    manifest = json.loads((bundle / "release-manifest.json").read_text(encoding="utf-8"))
    wheel = manifest["package"]
    (bundle / "wheel.sha256").write_text(
        f"{wheel['sha256']}  {wheel['filename']}\n", encoding="ascii"
    )

    result = _verify(bundle)

    assert result.returncode == 0, result.stderr


def test_release_verifier_keeps_cpython_only_locked_dependencies_for_linux_bundle(tmp_path):
    module = runpy.run_path(str(VERIFIER))
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "librt==0.15.0 ; platform_python_implementation != 'PyPy' \\\n"
        + "    --hash=sha256:"
        + "a" * 64
        + "\n",
        encoding="utf-8",
    )

    dependencies = module["_locked_dependencies"](lock)

    assert dependencies == {"librt": {"a" * 64}}


def test_release_verifier_rejects_a_server_wheel_or_tampered_installer_artifact(tmp_path):
    bundle = _deployment_bundle(tmp_path)
    (bundle / "skybeat_server-1.0.0-py3-none-any.whl").write_bytes(b"server wheel")

    server_wheel = _verify(bundle)

    assert server_wheel.returncode == 1
    assert "unapproved release artifact" in server_wheel.stderr

    (bundle / "skybeat_server-1.0.0-py3-none-any.whl").unlink()
    (bundle / "install-agent.sh").write_text("tampered\n", encoding="utf-8")

    tampered_tool = _verify(bundle)

    assert tampered_tool.returncode == 1
    assert "installer artifact sha256 mismatch" in tampered_tool.stderr


def test_release_verifier_rejects_a_declared_server_wheel_in_the_wheelhouse(tmp_path):
    bundle = _deployment_bundle(tmp_path)
    server_wheel = bundle / "wheelhouse" / "skybeat_server-1.0.0-py3-none-any.whl"
    server_wheel.write_bytes(b"server wheel")
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["wheelhouse"].append({"filename": server_wheel.name, "sha256": _sha256(server_wheel)})
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")

    result = _verify(bundle)

    assert result.returncode == 1
    assert "server wheel is not permitted" in result.stderr


def test_release_verifier_rejects_a_tampered_wheel_before_it_can_be_installed(tmp_path):
    bundle = _bundle(tmp_path)
    (bundle / "skybeat_agent-1.0.0-py3-none-any.whl").write_bytes(b"tampered")

    result = _verify(bundle)

    assert result.returncode == 1
    assert "sha256 mismatch" in result.stderr


def test_release_verifier_rejects_missing_locked_dependency_and_secret_like_manifest(tmp_path):
    bundle = _bundle(tmp_path)
    (bundle / "wheelhouse" / "psutil-1.0.0-py3-none-any.whl").unlink()

    missing = _verify(bundle)

    assert missing.returncode == 1
    assert "wheelhouse artifact is not a regular file" in missing.stderr

    bundle = _bundle(tmp_path / "secret")
    manifest_path = bundle / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["operator_note"] = "sb1.00000000-0000-0000-0000-000000000000." + "a" * 43
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    secret = _verify(bundle)

    assert secret.returncode == 1
    assert "secret-like value" in secret.stderr
    assert "sb1." not in secret.stderr


def test_release_verifier_rejects_a_secret_like_value_in_a_generic_release_artifact(tmp_path):
    bundle = _deployment_bundle(tmp_path)
    (bundle / "README.txt").write_text(
        "Enrollment credential: sbe1.00000000-0000-0000-0000-000000000000." + "a" * 43,
        encoding="utf-8",
    )
    _refresh_deployment_integrity(bundle)

    result = _verify(bundle)

    assert result.returncode == 1
    assert "release artifact contains secret-like value" in result.stderr
    assert "sbe1." not in result.stderr


def test_release_builder_uses_a_wheel_and_hash_locked_offline_wheelhouse_contract():
    script = BUILDER.read_text(encoding="utf-8")

    assert "uv build" in script
    assert "uv venv" in script
    assert "pip download" in script
    assert "--require-hashes" in script
    assert "release-manifest.json" in script
    assert 'sha256sum "$(basename "$wheel")" >"$bundle/wheel.sha256"' in script
    assert "pip install" not in script


def test_release_builder_stages_the_verified_self_contained_deployment_tooling():
    script = BUILDER.read_text(encoding="utf-8")

    assert "install-agent.sh" in script
    assert "skybeat_agent_install.sh" in script
    assert "validate-agent-server-url.py" in script
    assert "skybeat-agent-${version}-linux.zip" in script
    assert "SHA256SUMS" in script
    assert 'rm -f "$bundle/.gitignore"' in script


def test_agent_runtime_dependency_constraint_excludes_releases_without_linux_wheels():
    project = (ROOT / "agent" / "pyproject.toml").read_text(encoding="utf-8")

    assert '"psutil>=7,<7.1.2"' in project


def test_release_builder_uses_the_created_venv_interpreter_on_supported_host_layouts():
    script = BUILDER.read_text(encoding="utf-8")

    assert 'build_python="$staging/build-venv/bin/python"' in script
    assert 'build_python="$staging/build-venv/Scripts/python.exe"' in script
    assert '"$build_python" -m pip download' in script
    assert "--platform manylinux_2_17_x86_64" in script
    assert "--implementation cp" in script
    assert "--python-version 3.12" in script
    assert "--abi cp312" in script
    assert 'uv venv "$staging/build-venv" --python python3.12 --seed' in script
    assert '"$build_python" - "$bundle" "$wheel"' in script
