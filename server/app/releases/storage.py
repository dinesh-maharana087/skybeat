"""One durable release-store path policy for local and container runtimes."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.releases.service import ReleaseUnavailable


@dataclass(frozen=True)
class StorageStatus:
    available: bool
    writable: bool
    staging_ready: bool
    reason: str


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _canonical(root: Path) -> Path:
    if not root.is_absolute():
        raise ReleaseUnavailable("Release storage root must be an absolute path.")
    if ".." in root.parts:
        raise ReleaseUnavailable("Release storage root contains path traversal.")
    if root == Path(root.anchor):
        raise ReleaseUnavailable("Release storage root cannot be a filesystem root.")
    if any(_linked(part) for part in (root, *root.parents)):
        raise ReleaseUnavailable("Release storage root contains a linked directory.")
    try:
        canonical = root.resolve(strict=False)
    except (OSError, RuntimeError):
        raise ReleaseUnavailable("Release storage root cannot be resolved.") from None
    if canonical == Path(canonical.anchor):
        raise ReleaseUnavailable("Release storage root cannot be a filesystem root.")
    return canonical


def resolve_storage_root(
    configured: Path | None,
    environment: str,
    *,
    platform: str | None = None,
    variables: Mapping[str, str] | None = None,
    user_home: Path | None = None,
) -> Path | None:
    """Explicit roots win; development defaults are independent of the checkout."""
    if configured is not None:
        return _canonical(configured)
    if environment == "production":
        raise ReleaseUnavailable("Production requires an explicit durable release storage root.")
    if environment != "development":
        return None
    platform = platform or os.name
    variables = variables if variables is not None else os.environ
    home = user_home if user_home is not None else Path.home()
    if platform == "nt":
        candidate = (
            Path(variables.get("LOCALAPPDATA", "")) if variables.get("LOCALAPPDATA") else None
        )
        base = (
            candidate
            if candidate is not None and candidate.is_absolute()
            else home / "AppData" / "Local"
        )
        return _canonical(base / "SkyBeat" / "agent-releases")
    candidate = Path(variables.get("XDG_DATA_HOME", "")) if variables.get("XDG_DATA_HOME") else None
    base = (
        candidate
        if candidate is not None and candidate.is_absolute()
        else home / ".local" / "share"
    )
    return _canonical(base / "skybeat" / "agent-releases")


def prepare_storage(root: Path | None, *, development_default: bool) -> None:
    """Initialize only the dedicated default development root, without replacing files."""
    if not development_default or root is None:
        return
    root = _canonical(root)
    if root.name != "agent-releases" or root.parent.name.lower() != "skybeat":
        raise ReleaseUnavailable("Default release storage must use dedicated application data.")
    try:
        root.mkdir(parents=True, exist_ok=True)
        incoming = root / "incoming"
        if _linked(incoming):
            raise ReleaseUnavailable("Release staging directory is linked.")
        incoming.mkdir(exist_ok=True)
        _canonical(root)
    except OSError:
        raise ReleaseUnavailable("Default release storage could not be initialized.") from None


def inspect_storage(root: Path | None) -> StorageStatus:
    if root is None:
        return StorageStatus(False, False, False, "not configured")
    try:
        root = _canonical(root)
    except ReleaseUnavailable as exc:
        return StorageStatus(False, False, False, str(exc))
    if not root.is_dir():
        return StorageStatus(False, False, False, "configured directory is unavailable")
    incoming = root / "incoming"
    if _linked(incoming):
        return StorageStatus(True, False, False, "staging directory is linked")
    writable = _can_write(root)
    return StorageStatus(
        True,
        writable,
        incoming.is_dir() and _can_write(incoming),
        "available" if writable else "directory is not writable",
    )


def _can_write(directory: Path) -> bool:
    if not os.access(directory, os.W_OK):
        return False
    probe = directory / f".write-check-{uuid4().hex}"
    try:
        with probe.open("xb"):
            pass
        probe.unlink()
    except OSError:
        return False
    return True
