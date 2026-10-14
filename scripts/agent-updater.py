#!/usr/bin/env python3
"""Fixed root-owned one-shot lifecycle checker for this device only.

The server supplies an operation identifier and pinned digests, never commands,
paths, or URLs. The server/operator-approved repository is the release authority.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

CONFIG = Path("/etc/skybeat/agent.env")
STATE = Path("/var/lib/skybeat")
MARKER = STATE / "lifecycle.json"
INSTALL_MARKER = STATE / "install.marker"
OPT = Path("/opt/skybeat")
UNIT = Path("/etc/systemd/system/skybeat-agent.service")
TIMEOUT = 12
MAX_ARCHIVE = 128 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


class LocalFailure(Exception):
    """A safe local lifecycle failure category; never includes a credential."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        raise LocalFailure("redirects are not allowed")


def run(*args: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=timeout
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_config() -> dict[str, str]:
    if (
        CONFIG.is_symlink()
        or not CONFIG.is_file()
        or (
            os.name == "posix"
            and (CONFIG.stat().st_uid != 0 or CONFIG.stat().st_mode & 0o077)
        )
    ):
        raise LocalFailure("protected agent configuration is unavailable")
    values: dict[str, str] = {}
    for raw in CONFIG.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            key, sep, value = line.partition("=")
            if not sep or not key.startswith("SKYBEAT_") or key in values:
                raise LocalFailure("agent configuration is invalid")
            values[key] = value.strip('"')
    origin = values.get("SKYBEAT_SERVER_URL", "")
    parsed = urlsplit(origin)
    if (
        not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise LocalFailure("agent server origin is invalid")
    if parsed.scheme == "http":
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            raise LocalFailure("agent server origin is invalid") from None
        if values.get("SKYBEAT_ALLOW_INSECURE_LOCAL_SERVER") != "true" or not (
            address.is_private or address.is_loopback
        ):
            raise LocalFailure("agent server origin is invalid")
    elif parsed.scheme != "https":
        raise LocalFailure("agent server origin is invalid")
    if not re.fullmatch(
        r"sb1\.[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\.[A-Za-z0-9_-]{43}",
        values.get("SKYBEAT_DEVICE_TOKEN", ""),
    ):
        raise LocalFailure("device credential is invalid")
    if (
        str(uuid.UUID(values.get("SKYBEAT_DEVICE_ID", "")))
        != values["SKYBEAT_DEVICE_ID"]
    ):
        raise LocalFailure("device identity is invalid")
    return values


def request(
    values: dict[str, str], path: str, *, body: bytes | None = None, limit: int = 65536
) -> bytes:
    origin = values["SKYBEAT_SERVER_URL"].rstrip("/")
    opener = urllib.request.build_opener(NoRedirect())
    headers = {"Authorization": f"Bearer {values['SKYBEAT_DEVICE_TOKEN']}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(origin + path, data=body, headers=headers)
    with opener.open(req, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise LocalFailure("lifecycle server response is invalid")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise LocalFailure("lifecycle response exceeds limit")
    return data


def durable_write(path: Path, value: bytes) -> None:
    temporary = path.with_name(f".{path.name}.new")
    with temporary.open("wb") as output:
        if os.name == "posix":
            os.fchmod(output.fileno(), 0o600)
        output.write(value)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    if os.name == "posix":
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def save_marker(data: dict[str, object]) -> None:
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    durable_write(MARKER, (json.dumps(data, sort_keys=True) + "\n").encode("utf-8"))


def read_marker() -> dict[str, object] | None:
    if not MARKER.exists():
        return None
    if MARKER.is_symlink() or (
        os.name == "posix"
        and (MARKER.stat().st_uid != 0 or MARKER.stat().st_mode & 0o077)
    ):
        raise LocalFailure("local lifecycle marker is unsafe")
    data = json.loads(MARKER.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise LocalFailure("local lifecycle marker is invalid")
    return data


def operation(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise LocalFailure("lifecycle operation is invalid")
    allowed = {
        "operation_id",
        "action",
        "state",
        "target_version",
        "target_wheel_sha256",
        "archive_sha256",
        "previous_version",
        "failure_category",
        "rollback_available",
        "requested_at",
        "updated_at",
        "completed_at",
    }
    if set(value) - allowed:
        raise LocalFailure("lifecycle operation contains an unsupported field")
    fields = (
        "operation_id",
        "action",
        "state",
        "target_version",
        "target_wheel_sha256",
    )
    if any(not isinstance(value.get(key), str) for key in fields):
        raise LocalFailure("lifecycle operation is invalid")
    result = {key: value[key] for key in fields}
    if str(uuid.UUID(result["operation_id"])) != result["operation_id"]:
        raise LocalFailure("lifecycle operation identifier is invalid")
    if result["action"] not in {"UPGRADE", "ROLLBACK"} or result["state"] not in {
        "REQUESTED",
        "DOWNLOADING",
        "VERIFYING",
        "INSTALLING",
        "RESTARTING",
        "VERIFYING_HEALTH",
    }:
        raise LocalFailure("lifecycle operation is invalid")
    if not VERSION.fullmatch(result["target_version"]) or not HEX.fullmatch(
        result["target_wheel_sha256"]
    ):
        raise LocalFailure("lifecycle release identity is invalid")
    archive = value.get("archive_sha256")
    if result["action"] == "UPGRADE":
        if not isinstance(archive, str) or not HEX.fullmatch(archive):
            raise LocalFailure("pinned release digest is invalid")
        result["archive_sha256"] = archive
    elif archive is not None:
        raise LocalFailure("rollback release identity is invalid")
    return result


def report(
    values: dict[str, str], op: dict[str, str], state: str, **extra: object
) -> bool:
    payload = {"operation_id": op["operation_id"], "state": state, **extra}
    try:
        request(
            values, "/api/v1/agent-lifecycle/report", body=json.dumps(payload).encode()
        )
    except (OSError, urllib.error.URLError, LocalFailure):
        return False
    return True


def installed() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (OPT / "VERSION").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        result[key] = value
    return result


def local_health(expected_version: str, *, pause: int = 15) -> bool:
    try:
        if (
            run(
                str(OPT / "venv/bin/python"),
                "-c",
                'from importlib.metadata import version; print(version("skybeat-agent"))',
            ).stdout.strip()
            != expected_version
        ):
            return False
        config_check = (
            "import sys; from skybeat_agent.config import Config; "
            "lines=(line.strip() for line in open(sys.argv[1], encoding='utf-8')); "
            "Config.from_env(dict(line.split('=', 1) for line in lines if line and not line.startswith('#')))"
        )
        run(str(OPT / "venv/bin/python"), "-c", config_check, str(CONFIG))
        if not (
            CONFIG.is_file()
            and run(
                "/usr/bin/systemctl", "is-active", "skybeat-agent.service"
            ).stdout.strip()
            == "active"
        ):
            return False
        first = run(
            "/usr/bin/systemctl",
            "show",
            "skybeat-agent.service",
            "-p",
            "MainPID",
            "-p",
            "NRestarts",
        ).stdout
        import time

        time.sleep(pause)
        second = run(
            "/usr/bin/systemctl",
            "show",
            "skybeat-agent.service",
            "-p",
            "MainPID",
            "-p",
            "NRestarts",
        ).stdout
        return (
            first == second
            and re.search(r"^MainPID=[1-9][0-9]*$", first, re.MULTILINE) is not None
        )
    except (OSError, subprocess.SubprocessError, IndexError):
        return False


def extract_release(archive: Path, destination: Path, version: str) -> Path:
    root = f"skybeat-agent-{version}"
    total = 0
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 128 or len({entry.filename for entry in entries}) != len(
            entries
        ):
            raise LocalFailure("release archive member set is invalid")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (
                not path.parts
                or path.parts[0] != root
                or any(part in {"", ".", ".."} for part in path.parts)
                or path.is_absolute()
                or stat.S_ISLNK(entry.external_attr >> 16)
            ):
                raise LocalFailure("release archive contains an unsafe member")
            total += entry.file_size
            if total > MAX_ARCHIVE:
                raise LocalFailure("release archive exceeds limit")
        source.extractall(destination)
    return destination / root


def restore_candidate() -> bool:
    candidate = OPT / "venv.candidate"
    if not candidate.is_dir() or candidate.is_symlink():
        return False
    try:
        run("/usr/bin/systemctl", "stop", "skybeat-agent.service")
        current = OPT / "venv"
        action = "UPGRADE"
        if INSTALL_MARKER.is_file():
            action = dict(
                line.split("=", 1) for line in INSTALL_MARKER.read_text().splitlines()
            ).get("action", "UPGRADE")
        if action == "ROLLBACK":
            if current.exists():
                os.replace(current, OPT / "venv.previous")
            os.replace(candidate, current)
            candidate_record = OPT / "VERSION.candidate"
            if candidate_record.is_file():
                os.replace(candidate_record, OPT / "VERSION")
        else:
            if current.exists():
                shutil.rmtree(current)
            os.replace(candidate, current)
            previous_version_file = OPT / "VERSION.candidate"
            if previous_version_file.is_file():
                os.replace(previous_version_file, OPT / "VERSION")
        restore_unit = STATE / "skybeat-agent.service.candidate"
        if restore_unit.is_file():
            shutil.copy2(restore_unit, UNIT)
            run("/usr/bin/systemctl", "daemon-reload")
        run("/usr/bin/systemctl", "restart", "skybeat-agent.service")
        return local_health(installed()["version"])
    except (OSError, subprocess.SubprocessError, KeyError):
        return False


def recover_install() -> str:
    """Resolve a power loss during installer switch before contacting the server."""
    if not INSTALL_MARKER.exists():
        return "none"
    if INSTALL_MARKER.is_symlink() or (
        os.name == "posix"
        and (INSTALL_MARKER.stat().st_uid != 0 or INSTALL_MARKER.stat().st_mode & 0o077)
    ):
        raise LocalFailure("interrupted install marker is unsafe")
    record = dict(
        line.split("=", 1) for line in INSTALL_MARKER.read_text().splitlines()
    )
    phase = record.get("phase")
    target = record.get("target_sha256")
    if (
        phase
        not in {"STAGED", "SWITCHING", "SWITCHED", "ROLLED_BACK", "ROLLBACK_FAILED"}
        or not isinstance(target, str)
        or not HEX.fullmatch(target)
    ):
        raise LocalFailure("interrupted install marker is invalid")
    if phase == "STAGED":
        if (OPT / "venv.new").is_dir():
            shutil.rmtree(OPT / "venv.new")
        (OPT / "VERSION.candidate").unlink(missing_ok=True)
        (STATE / "skybeat-agent.service.candidate").unlink(missing_ok=True)
        INSTALL_MARKER.unlink()
        return "retry"
    if phase == "ROLLED_BACK":
        INSTALL_MARKER.unlink()
        return "rolled_back"
    if phase == "ROLLBACK_FAILED":
        return "rollback_failed"
    try:
        current = installed()
        if current.get("sha256") == target and local_health(current["version"]):
            previous = OPT / "venv.previous"
            if previous.is_dir() and (OPT / "venv.candidate").is_dir():
                shutil.rmtree(previous)
            candidate = OPT / "venv.candidate"
            if candidate.is_dir():
                os.replace(candidate, previous)
            if record.get("action") == "ROLLBACK":
                candidate_record = OPT / "VERSION.candidate"
                if candidate_record.is_file():
                    os.replace(candidate_record, OPT / "VERSION.previous")
                candidate_unit = STATE / "skybeat-agent.service.candidate"
                if candidate_unit.is_file():
                    os.replace(candidate_unit, STATE / "skybeat-agent.service.previous")
            else:
                candidate_record = OPT / "VERSION.candidate"
                if candidate_record.is_file():
                    os.replace(candidate_record, OPT / "VERSION.previous")
                candidate_unit = STATE / "skybeat-agent.service.candidate"
                if candidate_unit.is_file():
                    os.replace(candidate_unit, STATE / "skybeat-agent.service.previous")
            INSTALL_MARKER.unlink()
            return "succeeded"
    except (OSError, KeyError):
        pass
    try:
        current = installed()
        if current.get("sha256") == record.get("previous_sha256"):
            run("/usr/bin/systemctl", "start", "skybeat-agent.service")
            if local_health(current["version"]):
                INSTALL_MARKER.unlink()
                return "rolled_back"
    except (OSError, subprocess.SubprocessError, KeyError):
        pass
    if restore_candidate():
        INSTALL_MARKER.unlink()
        return "rolled_back"
    raise LocalFailure("interrupted install rollback failed")


def upgrade(
    values: dict[str, str], op: dict[str, str]
) -> tuple[str, dict[str, object]]:
    before = installed()
    if (
        before.get("version") == op["target_version"]
        and before.get("sha256") == op["target_wheel_sha256"]
    ):
        previous_record = OPT / "VERSION.previous"
        previous_digest = None
        if previous_record.is_file():
            previous_digest = dict(
                line.split("=", 1) for line in previous_record.read_text().splitlines()
            ).get("sha256")
        return "SUCCEEDED", {
            "previous_wheel_sha256": previous_digest,
            "rollback_available": previous_digest is not None
            and (OPT / "venv.previous").is_dir(),
        }
    report(values, op, "DOWNLOADING")
    with tempfile.TemporaryDirectory(prefix="skybeat-release-", dir=STATE) as temp:
        archive = Path(temp) / "release.zip"
        payload = request(
            values,
            f"/api/v1/agent-lifecycle/operation/{op['operation_id']}/download",
            limit=MAX_ARCHIVE,
        )
        archive.write_bytes(payload)
        if sha256(archive) != op["archive_sha256"]:
            return "FAILED", {
                "failure_category": "verification_failed",
                "failure_detail": "archive_digest_mismatch",
            }
        report(values, op, "VERIFYING")
        bundle = extract_release(archive, Path(temp), op["target_version"])
        try:
            run(
                "/usr/bin/python3.12",
                str(bundle / "verify-agent-release.py"),
                "--bundle",
                str(bundle),
            )
        except subprocess.SubprocessError:
            return "FAILED", {
                "failure_category": "verification_failed",
                "failure_detail": "bundle_verification_failed",
            }
        manifest = json.loads((bundle / "release-manifest.json").read_text())
        wheel = bundle / manifest["package"]["filename"]
        if manifest["package"]["sha256"] != op["target_wheel_sha256"]:
            return "FAILED", {
                "failure_category": "verification_failed",
                "failure_detail": "bundle_verification_failed",
            }
        report(values, op, "INSTALLING")
        arguments = [
            "/usr/bin/bash",
            str(bundle / "install-agent.sh"),
            "--server",
            values["SKYBEAT_SERVER_URL"],
            "--package",
            str(wheel),
            "--sha256",
            op["target_wheel_sha256"],
            "--wheelhouse",
            str(bundle / "wheelhouse"),
            "--lockfile",
            str(bundle / "requirements.lock"),
        ]
        if values.get("SKYBEAT_ALLOW_INSECURE_LOCAL_SERVER") == "true":
            arguments.append("--allow-insecure-local-server")
        try:
            run(*arguments, timeout=600)
        except (OSError, subprocess.SubprocessError):
            if local_health(before["version"], pause=2):
                return "ROLLED_BACK", {
                    "failure_category": "installation_failed",
                    "failure_detail": "installer_failed",
                }
            return "ROLLBACK_FAILED", {
                "failure_category": "rollback_failed",
                "failure_detail": "previous_service_unhealthy",
            }
    return "SUCCEEDED", {
        "previous_wheel_sha256": before.get("sha256"),
        "rollback_available": True,
    }


def rollback(op: dict[str, str]) -> tuple[str, dict[str, object]]:
    previous = OPT / "venv.previous"
    record = OPT / "VERSION.previous"
    if not previous.is_dir() or previous.is_symlink() or not record.is_file():
        return "FAILED", {
            "failure_category": "verification_failed",
            "failure_detail": "previous_release_mismatch",
        }
    values = dict(line.split("=", 1) for line in record.read_text().splitlines())
    if (
        values.get("sha256") != op["target_wheel_sha256"]
        or values.get("version") != op["target_version"]
    ):
        return "FAILED", {
            "failure_category": "verification_failed",
            "failure_detail": "previous_release_mismatch",
        }
    current = OPT / "venv"
    candidate = OPT / "venv.candidate"
    if candidate.exists() or INSTALL_MARKER.exists():
        return "FAILED", {
            "failure_category": "installation_failed",
            "failure_detail": "interrupted_switch",
        }
    current_record = OPT / "VERSION"
    candidate_record = OPT / "VERSION.candidate"
    candidate_unit = STATE / "skybeat-agent.service.candidate"
    previous_unit = STATE / "skybeat-agent.service.previous"
    marker = f"phase=SWITCHING\naction=ROLLBACK\ntarget_sha256={op['target_wheel_sha256']}\nprevious_sha256={installed().get('sha256', '')}\n"
    try:
        durable_write(INSTALL_MARKER, marker.encode("ascii"))
        shutil.copy2(current_record, candidate_record)
        shutil.copy2(UNIT, candidate_unit)
        run("/usr/bin/systemctl", "stop", "skybeat-agent.service")
        os.replace(current, candidate)
        os.replace(previous, current)
        current_record.write_bytes(record.read_bytes())
        if previous_unit.is_file():
            shutil.copy2(previous_unit, UNIT)
            run("/usr/bin/systemctl", "daemon-reload")
        run("/usr/bin/systemctl", "restart", "skybeat-agent.service")
        if local_health(op["target_version"]):
            os.replace(candidate, previous)
            os.replace(candidate_record, record)
            os.replace(candidate_unit, previous_unit)
            INSTALL_MARKER.unlink()
            return "ROLLED_BACK", {}
    except (OSError, subprocess.SubprocessError):
        pass
    if restore_candidate():
        INSTALL_MARKER.unlink(missing_ok=True)
        return "FAILED", {
            "failure_category": "health_check_failed",
            "failure_detail": "rollback_target_unhealthy",
        }
    if local_health(installed().get("version", ""), pause=2):
        INSTALL_MARKER.unlink(missing_ok=True)
        return "FAILED", {
            "failure_category": "installation_failed",
            "failure_detail": "interrupted_switch",
        }
    return "ROLLBACK_FAILED", {
        "failure_category": "rollback_failed",
        "failure_detail": "previous_service_unhealthy",
    }


def main() -> int:
    import fcntl

    if os.geteuid() != 0:
        print("agent-updater: root is required", file=sys.stderr)
        return 1
    if STATE.is_symlink():
        print("agent-updater: local state directory is unsafe", file=sys.stderr)
        return 1
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o022:
        print("agent-updater: local state directory is unsafe", file=sys.stderr)
        return 1
    if sys.argv[1:] == ["--recover-local"]:
        try:
            outcome = recover_install()
        except (OSError, ValueError, KeyError, LocalFailure):
            print("agent-updater: local recovery failed", file=sys.stderr)
            return 1
        if outcome == "rollback_failed":
            print(
                "agent-updater: previous agent requires local repair", file=sys.stderr
            )
            return 1
        print(f"agent-updater: local recovery {outcome}")
        return 0
    if sys.argv[1:]:
        print("agent-updater: unsupported local argument", file=sys.stderr)
        return 64
    with (STATE / "updater.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            values = read_config()
            recovered = recover_install()
            pending = read_marker()
            if pending is not None:
                op = operation(pending["operation"])
                final = pending.get("final")
                if final is None:
                    if recovered == "succeeded":
                        if op["action"] == "UPGRADE":
                            final = {
                                "state": "SUCCEEDED",
                                "previous_wheel_sha256": pending.get("previous_sha256"),
                                "rollback_available": (OPT / "venv.previous").is_dir(),
                            }
                        else:
                            final = {"state": "ROLLED_BACK"}
                    elif recovered == "rolled_back":
                        final = (
                            {
                                "state": "ROLLED_BACK",
                                "failure_category": "installation_failed",
                                "failure_detail": "interrupted_switch",
                            }
                            if op["action"] == "UPGRADE"
                            else {
                                "state": "FAILED",
                                "failure_category": "health_check_failed",
                                "failure_detail": "rollback_target_unhealthy",
                            }
                        )
                    elif recovered == "rollback_failed":
                        final = {
                            "state": "ROLLBACK_FAILED",
                            "failure_category": "rollback_failed",
                            "failure_detail": "previous_service_unhealthy",
                        }
                    else:
                        if op["action"] == "UPGRADE":
                            state, detail = upgrade(values, op)
                        else:
                            state, detail = rollback(op)
                        final = {"state": state, **detail}
                    pending["final"] = final
                    save_marker(pending)
                if isinstance(final, dict) and report(
                    values,
                    op,
                    str(final["state"]),
                    **{
                        k: v for k, v in final.items() if k != "state" and v is not None
                    },
                ):
                    MARKER.unlink()
                return 0
            response = json.loads(request(values, "/api/v1/agent-lifecycle/operation"))
            item = response.get("operation")
            if item is None:
                return 0
            op = operation(item)
            before = installed()
            save_marker({"operation": op, "previous_sha256": before.get("sha256")})
            if op["action"] == "UPGRADE":
                state, detail = upgrade(values, op)
            else:
                state, detail = rollback(op)
            marker = {"operation": op, "final": {"state": state, **detail}}
            save_marker(marker)
            if report(values, op, state, **detail):
                MARKER.unlink()
            return 0
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            urllib.error.URLError,
            LocalFailure,
            zipfile.BadZipFile,
        ) as error:
            # Deliberately omit exception text: urllib errors can contain the server URL.
            print(f"agent-updater: {type(error).__name__}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
