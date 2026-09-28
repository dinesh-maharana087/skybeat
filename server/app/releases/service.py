"""Safe boundary for the configured immutable agent release."""

import hashlib
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SECRET_BYTES_PATTERN = re.compile(rb"\b(?:sb1|sbe1|sbv1)\.[A-Za-z0-9_-]+\.")


class ReleaseUnavailable(ValueError):
    """The configured release cannot safely be served."""


@dataclass(frozen=True)
class ReleaseMetadata:
    version: str
    wheel_filename: str
    wheel_sha256: str
    archive_filename: str
    archive_root: str
    server_url: str
    allow_insecure_local_server: bool


class AgentReleaseService:
    def __init__(self, release_dir: Path | None, server_url: str) -> None:
        self._release_dir = release_dir
        self._server_url = server_url

    def current(self) -> ReleaseMetadata:
        metadata, _ = self._validated_release()
        return metadata

    def archive(self) -> Path:
        metadata, files = self._validated_release()
        directory = self._release_dir
        if directory is None:
            raise ReleaseUnavailable("Agent release is unavailable.")
        archive = directory.parent / metadata.archive_filename
        if archive.is_symlink() or not archive.is_file():
            raise ReleaseUnavailable("Agent release is unavailable.")
        expected = {f"{metadata.archive_root}/{filename}" for filename in files}
        try:
            with zipfile.ZipFile(archive) as source:
                entries = [entry for entry in source.infolist() if not entry.is_dir()]
                names = [entry.filename for entry in entries]
                if len(names) != len(set(names)) or set(names) != expected:
                    raise ReleaseUnavailable("Agent release is unavailable.")
                for entry in entries:
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        raise ReleaseUnavailable("Agent release is unavailable.")
                    relative = entry.filename.removeprefix(f"{metadata.archive_root}/")
                    if self._digest_stream(source.open(entry)) != self._digest_file(
                        directory / relative
                    ):
                        raise ReleaseUnavailable("Agent release is unavailable.")
        except (OSError, zipfile.BadZipFile):
            raise ReleaseUnavailable("Agent release is unavailable.") from None
        return archive

    def _validated_release(self) -> tuple[ReleaseMetadata, set[str]]:
        directory = self._release_dir
        if (
            directory is None
            or not directory.is_absolute()
            or directory.is_symlink()
            or not directory.is_dir()
        ):
            raise ReleaseUnavailable("Agent release is unavailable.")
        manifest_path = directory / "release-manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise ReleaseUnavailable("Agent release is unavailable.") from None
        if (
            not isinstance(manifest, dict)
            or set(manifest)
            != {
                "format",
                "package",
                "requirements_lock",
                "wheelhouse",
                "installer_artifacts",
            }
            or manifest.get("format") != 2
        ):
            raise ReleaseUnavailable("Agent release is unavailable.")
        package = self._mapping(manifest["package"])
        lock = self._mapping(manifest["requirements_lock"])
        version = self._text(package.get("version"))
        wheel_filename = self._filename(package.get("filename"))
        wheel_sha256 = self._digest(package.get("sha256"))
        if (
            package.get("name") != "skybeat-agent"
            or not wheel_filename.startswith(f"skybeat_agent-{version}-")
            or not wheel_filename.endswith(".whl")
        ):
            raise ReleaseUnavailable("Agent release is unavailable.")
        files = {"release-manifest.json", "wheel.sha256", "SHA256SUMS", wheel_filename}
        self._checked_file(directory, wheel_filename, wheel_sha256)
        self._checked_agent_wheel(directory / wheel_filename, version)
        lock_filename = self._filename(lock.get("filename"))
        lock_sha256 = self._digest(lock.get("sha256"))
        files.add(lock_filename)
        self._checked_file(directory, lock_filename, lock_sha256)
        installer_artifacts: dict[str, str] = {}
        for record in self._records(manifest["installer_artifacts"]):
            filename = self._relative_filename(record.get("filename"))
            digest = self._digest(record.get("sha256"))
            if filename in installer_artifacts:
                raise ReleaseUnavailable("Agent release is unavailable.")
            installer_artifacts[filename] = digest
            files.add(filename)
            self._checked_file(directory, filename, digest)
        for record in self._records(manifest["wheelhouse"]):
            filename = self._filename(record.get("filename"))
            if self._is_server_wheel(filename):
                raise ReleaseUnavailable("Agent release is unavailable.")
            files.add(f"wheelhouse/{filename}")
            self._checked_file(
                directory / "wheelhouse", filename, self._digest(record.get("sha256"))
            )
        self._checked_checksum_files(
            directory,
            wheel_filename=wheel_filename,
            wheel_sha256=wheel_sha256,
            lock_filename=lock_filename,
            lock_sha256=lock_sha256,
            installer_artifacts=installer_artifacts,
        )
        actual = {
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file() and not path.is_symlink()
        }
        if actual != files:
            raise ReleaseUnavailable("Agent release is unavailable.")
        if any(self._contains_secret_like_value(directory / filename) for filename in files):
            raise ReleaseUnavailable("Agent release is unavailable.")
        return (
            ReleaseMetadata(
                version=version,
                wheel_filename=wheel_filename,
                wheel_sha256=wheel_sha256,
                archive_filename=f"{directory.name}-linux.zip",
                archive_root=directory.name,
                server_url=self._server_url,
                allow_insecure_local_server=self._server_url.startswith("http://"),
            ),
            files,
        )

    @staticmethod
    def _mapping(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ReleaseUnavailable("Agent release is unavailable.")
        return value

    @staticmethod
    def _records(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not value:
            raise ReleaseUnavailable("Agent release is unavailable.")
        return [AgentReleaseService._mapping(record) for record in value]

    @staticmethod
    def _text(value: object) -> str:
        if not isinstance(value, str) or not value:
            raise ReleaseUnavailable("Agent release is unavailable.")
        return value

    @classmethod
    def _filename(cls, value: object) -> str:
        filename = cls._text(value)
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ReleaseUnavailable("Agent release is unavailable.")
        return filename

    @classmethod
    def _relative_filename(cls, value: object) -> str:
        filename = cls._text(value)
        path = PurePosixPath(filename)
        if (
            "\\" in filename
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ReleaseUnavailable("Agent release is unavailable.")
        return filename

    @staticmethod
    def _digest(value: object) -> str:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise ReleaseUnavailable("Agent release is unavailable.")
        return value

    @staticmethod
    def _is_server_wheel(filename: str) -> bool:
        return re.sub(r"[-_.]+", "-", filename).lower().startswith("skybeat-server-")

    @classmethod
    def _checked_checksum_files(
        cls,
        directory: Path,
        *,
        wheel_filename: str,
        wheel_sha256: str,
        lock_filename: str,
        lock_sha256: str,
        installer_artifacts: dict[str, str],
    ) -> None:
        wheel_record = directory / "wheel.sha256"
        checksums = directory / "SHA256SUMS"
        try:
            if (
                wheel_record.is_symlink()
                or wheel_record.read_text(encoding="ascii")
                not in {
                    f"{wheel_sha256} *{wheel_filename}\n",
                    f"{wheel_sha256}  {wheel_filename}\n",
                }
                or checksums.is_symlink()
            ):
                raise ReleaseUnavailable("Agent release is unavailable.")
            parsed: dict[str, str] = {}
            for line in checksums.read_text(encoding="ascii").splitlines():
                match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)", line)
                if match is None:
                    raise ReleaseUnavailable("Agent release is unavailable.")
                filename = cls._relative_filename(match.group(2))
                if filename in parsed:
                    raise ReleaseUnavailable("Agent release is unavailable.")
                parsed[filename] = match.group(1)
        except (OSError, UnicodeDecodeError):
            raise ReleaseUnavailable("Agent release is unavailable.") from None
        if parsed != {
            wheel_filename: wheel_sha256,
            lock_filename: lock_sha256,
            **installer_artifacts,
        }:
            raise ReleaseUnavailable("Agent release is unavailable.")

    @classmethod
    def _checked_file(cls, directory: Path, filename: str, expected: str) -> None:
        path = directory / filename
        if path.is_symlink() or not path.is_file() or cls._digest_file(path) != expected:
            raise ReleaseUnavailable("Agent release is unavailable.")

    @staticmethod
    def _digest_file(path: Path) -> str:
        with path.open("rb") as source:
            return AgentReleaseService._digest_stream(source)

    @staticmethod
    def _checked_agent_wheel(wheel: Path, version: str) -> None:
        try:
            with zipfile.ZipFile(wheel) as archive:
                metadata_files = [
                    member
                    for member in archive.namelist()
                    if member.endswith(".dist-info/METADATA")
                ]
                if len(metadata_files) != 1:
                    raise ReleaseUnavailable("Agent release is unavailable.")
                fields = dict(
                    line.split(": ", 1)
                    for line in archive.read(metadata_files[0]).decode("utf-8").splitlines()
                    if line.startswith(("Name: ", "Version: "))
                )
        except (OSError, UnicodeDecodeError, zipfile.BadZipFile):
            raise ReleaseUnavailable("Agent release is unavailable.") from None
        if fields.get("Name") != "skybeat-agent" or fields.get("Version") != version:
            raise ReleaseUnavailable("Agent release is unavailable.")

    @staticmethod
    def _digest_stream(source: Any) -> str:
        digest = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _contains_secret_like_value(path: Path) -> bool:
        trailing = b""
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                candidate = trailing + chunk
                if SECRET_BYTES_PATTERN.search(candidate):
                    return True
                trailing = candidate[-128:]
        return False
