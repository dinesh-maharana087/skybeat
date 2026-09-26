#!/usr/bin/env python3
"""Verify a reviewed local SkyBeat agent release bundle without installing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, NoReturn, cast

SECRET_PATTERN = re.compile(r"\b(?:sb1|sbe1|sbv1)\.[A-Za-z0-9_-]+\.")
PACKAGE_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==[^\s\\]+")
HASH_PATTERN = re.compile(r"--hash=sha256:([0-9a-f]{64})")


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


def _digest(value: object, label: str) -> str:
    digest = _text(value, label)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        _fail(f"{label} is invalid")
    return digest


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _manifest_file(bundle: Path, record: dict[str, Any], label: str) -> Path:
    filename = _filename(record.get("filename"), f"{label} filename")
    expected = _digest(record.get("sha256"), f"{label} sha256")
    path = bundle / filename
    _regular_file(path, label)
    if _sha256(path) != expected:
        _fail(f"{label} sha256 mismatch")
    return path


def _locked_dependencies(lockfile: Path) -> dict[str, set[str]]:
    dependencies: dict[str, set[str]] = {}
    active: str | None = None
    for raw_line in lockfile.read_text(encoding="utf-8").splitlines():
        match = PACKAGE_LINE.match(raw_line)
        if match is not None:
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
    if set(manifest) != {"format", "package", "requirements_lock", "wheelhouse"}:
        _fail("release manifest is invalid")
    if manifest.get("format") != 1:
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
