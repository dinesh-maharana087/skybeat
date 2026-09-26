"""Release bundle contract tests; no network or production artifacts are used."""

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "verify-agent-release.py"
BUILDER = ROOT / "scripts" / "build-agent-release.sh"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path) -> Path:
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
    lock.write_text("psutil==1.0.0 --hash=sha256:" + _sha256(dependency) + "\n", encoding="utf-8")
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


def test_release_builder_uses_a_wheel_and_hash_locked_offline_wheelhouse_contract():
    script = BUILDER.read_text(encoding="utf-8")

    assert "uv build" in script
    assert "uv venv" in script
    assert "pip download" in script
    assert "--require-hashes" in script
    assert "release-manifest.json" in script
    assert 'sha256sum "$(basename "$wheel")" >"$bundle/wheel.sha256"' in script
    assert "pip install" not in script


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
