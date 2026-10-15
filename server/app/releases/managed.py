"""Immutable, content-addressed storage for verified offline agent releases."""

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.releases.service import AgentReleaseService, ReleaseMetadata, ReleaseUnavailable
from app.releases.storage import resolve_storage_root

NAME = re.compile(r"skybeat-agent-[0-9]+\.[0-9]+\.[0-9]+\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
STORE_KEY_LENGTH = 32


@dataclass(frozen=True)
class StoredRelease:
    version: str
    wheel_sha256: str
    archive_sha256: str
    bundle: Path
    archive: Path
    metadata: ReleaseMetadata


class ReleaseStore:
    def __init__(self, root: Path | None, server_url: str) -> None:
        self.root = root
        self.server_url = server_url

    @staticmethod
    def _linked(path: Path) -> bool:
        return path.is_symlink() or path.is_junction()

    def _root(self) -> Path:
        if self.root is None:
            raise ReleaseUnavailable("Agent release storage is not configured.")
        root = resolve_storage_root(self.root, "test")
        if root is None:
            raise ReleaseUnavailable("Agent release storage is not configured.")
        if os.name == "nt" and not str(root).startswith("\\\\?\\"):
            if str(root).startswith("\\\\"):
                return Path("\\\\?\\UNC\\" + str(root)[2:])
            return Path("\\\\?\\" + str(root))
        return root

    @staticmethod
    def _safe_tree(directory: Path) -> None:
        if ReleaseStore._linked(directory) or not directory.is_dir():
            raise ReleaseUnavailable("Agent release is unavailable.")
        if any(ReleaseStore._linked(path) for path in directory.rglob("*")):
            raise ReleaseUnavailable("Agent release is unavailable.")

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            raise ReleaseUnavailable("Agent release is unavailable.") from None
        return digest.hexdigest()

    def _validated(self, bundle: Path) -> StoredRelease:
        try:
            self._safe_tree(bundle)
            service = AgentReleaseService(bundle, self.server_url)
            metadata = service.current()
            archive = service.archive()
            if bundle.name != f"skybeat-agent-{metadata.version}":
                raise ReleaseUnavailable("Agent release name does not match its manifest version.")
            return StoredRelease(
                metadata.version,
                metadata.wheel_sha256,
                self._hash(archive),
                bundle,
                archive,
                metadata,
            )
        except OSError:
            raise ReleaseUnavailable("Agent release artifact could not be read.") from None

    def import_candidate(self, name: str) -> StoredRelease:
        if NAME.fullmatch(name) is None:
            raise ReleaseUnavailable("Agent release name is invalid.")
        root = self._root()
        incoming = root / "incoming"
        if self._linked(incoming) or not incoming.is_dir():
            raise ReleaseUnavailable("Agent release staging area is unavailable.")
        source = incoming / name
        candidate = self._validated(source)
        if self._linked(candidate.archive):
            raise ReleaseUnavailable("Agent release is unavailable.")
        objects = root / "objects"
        if self._linked(objects):
            raise ReleaseUnavailable("Agent release storage is unavailable.")
        objects.mkdir(exist_ok=True)
        destination = objects / candidate.archive_sha256[:STORE_KEY_LENGTH]
        if destination.exists():
            stored = self.validate(candidate.archive_sha256)
            if stored.version != candidate.version or stored.wheel_sha256 != candidate.wheel_sha256:
                raise ReleaseUnavailable("Agent release identity conflicts with stored bytes.")
            return stored
        temporary = objects / f".import-{uuid4().hex}"
        try:
            temporary.mkdir()
            shutil.copytree(source, temporary / name)
            shutil.copy2(candidate.archive, temporary / candidate.archive.name)
            copied = self._validated(temporary / name)
            if copied.archive_sha256 != candidate.archive_sha256:
                raise ReleaseUnavailable("Agent release changed during import.")
            try:
                os.rename(temporary, destination)
            except FileExistsError:
                pass
            return self.validate(candidate.archive_sha256)
        except (OSError, shutil.Error):
            raise ReleaseUnavailable("Agent release could not be imported.") from None
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def validate(self, digest: str) -> StoredRelease:
        if DIGEST.fullmatch(digest) is None:
            raise ReleaseUnavailable("Agent release identity is invalid.")
        objects = self._root() / "objects"
        if self._linked(objects):
            raise ReleaseUnavailable("Agent release storage is unavailable.")
        directory = objects / digest[:STORE_KEY_LENGTH]
        if not directory.exists():
            raise ReleaseUnavailable("Stored release artifact is missing.")
        self._safe_tree(directory)
        bundles = [
            path for path in directory.iterdir() if path.is_dir() and NAME.fullmatch(path.name)
        ]
        if len(bundles) != 1:
            raise ReleaseUnavailable("Agent release is unavailable.")
        artifact = self._validated(bundles[0])
        if artifact.archive_sha256 != digest:
            raise ReleaseUnavailable("Agent release digest does not match stored bytes.")
        return artifact
