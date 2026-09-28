#!/usr/bin/env python3
"""Verify a reviewed local SkyBeat agent release bundle without installing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

SECRET_PATTERN = re.compile(r"\b(?:sb1|sbe1|sbv1)\.[A-Za-z0-9_-]+\.")
SECRET_BYTES_PATTERN = re.compile(rb"\b(?:sb1|sbe1|sbv1)\.[A-Za-z0-9_-]+\.")
PACKAGE_LINE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==[^\s\\;]+(?:\s*;\s*([^\\]+?))?"
    r"(?:\s+--hash=sha256:[0-9a-f]{64})*\s*(?:\\)?$"
)
HASH_PATTERN = re.compile(r"--hash=sha256:([0-9a-f]{64})")
SHA256SUM_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9_./-]+)$")

INSTALLER_ARTIFACTS = frozenset(
    {
        "install-agent.sh",
        "lib/skybeat_agent_install.sh",
        "verify-agent-release.py",
        "validate-agent-server-url.py",
        "deployment/systemd/skybeat-agent.service",
        "README.txt",
    }
)


class VerificationError(ValueError):
    """A safe operator-facing release verification error."""


def _fail(message: str) -> NoReturn:
    raise VerificationError(message)


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        _fail(f"{label} is not a regular file")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contains_secret_like_value(path: Path) -> bool:
    """Search binary artifacts without copying a whole release artifact into memory."""
    trailing = b""
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            candidate = trailing + chunk
            if SECRET_BYTES_PATTERN.search(candidate):
                return True
            trailing = candidate[-128:]
    return False


def _reject_secret_like_artifacts(bundle: Path) -> None:
    for path in bundle.rglob("*"):
        if path.is_file() and not path.is_symlink() and _contains_secret_like_value(path):
            _fail("release artifact contains secret-like value")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _fail(f"{label} is invalid")
    return cast(dict[str, Any], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} is invalid")
    return value


def _filename(value: object, label: str) -> str:
    name = _text(value, label)
    if Path(name).name != name or name in {".", ".."}:
        _fail(f"{label} is invalid")
    return name


def _relative_filename(value: object, label: str) -> str:
    name = _text(value, label)
    path = PurePosixPath(name)
    if (
        "\\" in name
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _fail(f"{label} is invalid")
    return name


def _digest(value: object, label: str) -> str:
    digest = _text(value, label)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        _fail(f"{label} is invalid")
    return digest


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _is_server_wheel(filename: str) -> bool:
    return _normalise(filename).startswith("skybeat-server-")


def _manifest_file(bundle: Path, record: dict[str, Any], label: str) -> Path:
    filename = _filename(record.get("filename"), f"{label} filename")
    expected = _digest(record.get("sha256"), f"{label} sha256")
    path = bundle / filename
    _regular_file(path, label)
    if _sha256(path) != expected:
        _fail(f"{label} sha256 mismatch")
    return path


def _installer_artifacts(bundle: Path, value: object) -> dict[str, str]:
    if not isinstance(value, list):
        _fail("installer artifacts are invalid")
    artifacts: dict[str, str] = {}
    for item in value:
        record = _mapping(item, "installer artifact")
        if set(record) != {"filename", "sha256"}:
            _fail("installer artifact is invalid")
        filename = _relative_filename(record.get("filename"), "installer artifact filename")
        expected = _digest(record.get("sha256"), "installer artifact sha256")
        if filename in artifacts:
            _fail("installer artifacts are invalid")
        path = bundle / filename
        _regular_file(path, "installer artifact")
        if _sha256(path) != expected:
            _fail("installer artifact sha256 mismatch")
        artifacts[filename] = expected
    if set(artifacts) != INSTALLER_ARTIFACTS:
        _fail("installer artifacts are invalid")
    return artifacts


def _verify_deployment_files(
    bundle: Path,
    *,
    package: dict[str, Any],
    lock: dict[str, Any],
    wheelhouse: dict[str, str],
    installer_artifacts: dict[str, str],
) -> None:
    package_filename = _filename(package.get("filename"), "package filename")
    package_sha256 = _digest(package.get("sha256"), "package sha256")
    lock_filename = _filename(lock.get("filename"), "requirements lock filename")
    lock_sha256 = _digest(lock.get("sha256"), "requirements lock sha256")
    wheel_hash_record = bundle / "wheel.sha256"
    _regular_file(wheel_hash_record, "wheel sha256")
    if wheel_hash_record.read_text(encoding="ascii") not in {
        f"{package_sha256} *{package_filename}\n",
        f"{package_sha256}  {package_filename}\n",
    }:
        _fail("wheel sha256 is invalid")

    checksum_file = bundle / "SHA256SUMS"
    _regular_file(checksum_file, "SHA256SUMS")
    sums: dict[str, str] = {}
    try:
        lines = checksum_file.read_text(encoding="ascii").splitlines()
    except UnicodeDecodeError:
        _fail("SHA256SUMS is invalid")
    for line in lines:
        match = SHA256SUM_LINE.fullmatch(line)
        if match is None:
            _fail("SHA256SUMS is invalid")
        filename = _relative_filename(match.group(2), "SHA256SUMS filename")
        if filename in sums:
            _fail("SHA256SUMS is invalid")
        sums[filename] = match.group(1)
    expected_sums = {
        package_filename: package_sha256,
        lock_filename: lock_sha256,
        **installer_artifacts,
    }
    if sums != expected_sums:
        _fail("SHA256SUMS is invalid")

    expected_files = {
        "release-manifest.json",
        "wheel.sha256",
        "SHA256SUMS",
        package_filename,
        lock_filename,
        *installer_artifacts,
        *(f"wheelhouse/{filename}" for filename in wheelhouse),
    }
    actual_files: set[str] = set()
    for path in bundle.rglob("*"):
        if path.is_symlink():
            _fail("unapproved release artifact")
        if path.is_file():
            actual_files.add(path.relative_to(bundle).as_posix())
    if actual_files != expected_files:
        _fail("unapproved release artifact")


def _locked_dependencies(lockfile: Path) -> dict[str, set[str]]:
    dependencies: dict[str, set[str]] = {}
    active: str | None = None
    for raw_line in lockfile.read_text(encoding="utf-8").splitlines():
        match = PACKAGE_LINE.match(raw_line)
        if match is not None:
            marker = match.group(2)
            if marker is not None:
                normalized_marker = " ".join(marker.split())
                if normalized_marker in {
                    "sys_platform == 'win32'",
                    'sys_platform == "win32"',
                }:
                    active = None
                    continue
                if normalized_marker not in {
                    "platform_python_implementation != 'PyPy'",
                    'platform_python_implementation != "PyPy"',
                }:
                    _fail("requirements lock marker is unsupported")
            active = _normalise(match.group(1))
            dependencies.setdefault(active, set()).update(HASH_PATTERN.findall(raw_line))
            continue
        if active is not None:
            dependencies[active].update(HASH_PATTERN.findall(raw_line))
        if (
            raw_line
            and not raw_line.rstrip().endswith("\\")
            and not raw_line.lstrip().startswith("#")
        ):
            active = None
    if not dependencies or any(not hashes for hashes in dependencies.values()):
        _fail("requirements lock is incomplete")
    return dependencies


def _wheel_metadata(wheel: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata_files = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1:
                _fail("package wheel metadata is invalid")
            metadata = archive.read(metadata_files[0]).decode("utf-8")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile):
        _fail("package wheel metadata is invalid")
    fields = dict(
        line.split(": ", 1)
        for line in metadata.splitlines()
        if line.startswith(("Name: ", "Version: "))
    )
    return _text(fields.get("Name"), "package name"), _text(
        fields.get("Version"), "package version"
    )


def verify(bundle: Path) -> None:
    if bundle.is_symlink() or not bundle.is_dir():
        _fail("release bundle directory is invalid")
    manifest_path = bundle / "release-manifest.json"
    _regular_file(manifest_path, "release manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail("release manifest is invalid")
    if SECRET_PATTERN.search(json.dumps(manifest, sort_keys=True)):
        _fail("release manifest contains secret-like value")
    manifest = _mapping(manifest, "release manifest")
    if manifest.get("format") not in {1, 2}:
        _fail("release manifest is invalid")
    expected_keys = {"format", "package", "requirements_lock", "wheelhouse"}
    if manifest.get("format") == 2:
        expected_keys.add("installer_artifacts")
    if set(manifest) != expected_keys:
        _fail("release manifest format is invalid")
    package = _mapping(manifest.get("package"), "package")
    if set(package) != {"name", "version", "filename", "sha256"}:
        _fail("package is invalid")
    wheel = _manifest_file(bundle, package, "package wheel")
    if wheel.suffix != ".whl":
        _fail("package wheel is invalid")
    name, version = _wheel_metadata(wheel)
    if name != _text(package.get("name"), "package name") or version != _text(
        package.get("version"), "package version"
    ):
        _fail("package wheel metadata does not match manifest")
    if not wheel.name.startswith(f"skybeat_agent-{version}-"):
        _fail("package wheel filename is invalid")

    lock_record = _mapping(manifest.get("requirements_lock"), "requirements lock")
    if set(lock_record) != {"filename", "sha256"}:
        _fail("requirements lock is invalid")
    lockfile = _manifest_file(bundle, lock_record, "requirements lock")
    if SECRET_PATTERN.search(lockfile.read_text(encoding="utf-8")):
        _fail("requirements lock contains secret-like value")
    dependencies = _locked_dependencies(lockfile)

    wheelhouse = manifest.get("wheelhouse")
    if not isinstance(wheelhouse, list) or not wheelhouse:
        _fail("wheelhouse is invalid")
    artifact_hashes: dict[str, str] = {}
    for item in wheelhouse:
        record = _mapping(item, "wheelhouse artifact")
        if set(record) != {"filename", "sha256"}:
            _fail("wheelhouse artifact is invalid")
        artifact = _manifest_file(bundle / "wheelhouse", record, "wheelhouse artifact")
        if artifact.suffix != ".whl":
            _fail("wheelhouse artifact is invalid")
        if _is_server_wheel(artifact.name):
            _fail("server wheel is not permitted")
        artifact_hashes[artifact.name] = _sha256(artifact)
    wheelhouse_dir = bundle / "wheelhouse"
    if wheelhouse_dir.is_symlink() or not wheelhouse_dir.is_dir():
        _fail("wheelhouse is invalid")
    if {path.name for path in wheelhouse_dir.iterdir()} != set(artifact_hashes):
        _fail("wheelhouse contains unapproved artifact")
    for dependency, hashes in dependencies.items():
        matches = [
            digest
            for filename, digest in artifact_hashes.items()
            if _normalise(filename).startswith(f"{dependency}-")
        ]
        if not matches:
            _fail("locked dependency artifact is missing")
        if not any(digest in hashes for digest in matches):
            _fail("locked dependency artifact sha256 mismatch")

    if manifest["format"] == 2:
        installer_artifacts = _installer_artifacts(bundle, manifest["installer_artifacts"])
        _verify_deployment_files(
            bundle,
            package=package,
            lock=lock_record,
            wheelhouse=artifact_hashes,
            installer_artifacts=installer_artifacts,
        )
    _reject_secret_like_artifacts(bundle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        verify(arguments.bundle)
    except VerificationError as error:
        print(f"verify-agent-release: {error}", file=sys.stderr)
        return 1
    print("SkyBeat agent release bundle is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
