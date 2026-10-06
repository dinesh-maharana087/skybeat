"""Fixed, bounded journald snapshots for Log Watch."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from skybeat_agent.collectors.process import BoundedProcess

SOURCES = ("skybeat_agent", "system_journal", "kernel")
MAX_UPLOAD_ENTRIES = 80
MAX_MESSAGE_CHARS = 2048
MAX_MESSAGE_BYTES_TOTAL = 48 * 1024
_SEVERITIES = ("emergency", "alert", "critical", "error", "warning", "notice", "info", "debug")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def _message(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    safe = (
        _CONTROL.sub(" ", _ANSI.sub("", value)).encode("utf-8", "replace").decode("utf-8").strip()
    )
    if not safe:
        return None
    return safe[:MAX_MESSAGE_CHARS]


def _occurred_at(value: object) -> str | None:
    try:
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
            return None
        stamp = int(value)
        return datetime.fromtimestamp(stamp / 1_000_000, UTC).isoformat().replace("+00:00", "Z")
    except (OverflowError, ValueError, OSError):
        return None


def parse_journal(output: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    total = 0
    for line in output.splitlines():
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        cursor = record.get("__CURSOR")
        message = _message(record.get("MESSAGE"))
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 1024 or message is None:
            continue
        try:
            digest = hashlib.sha256(cursor.encode("utf-8")).hexdigest()
        except UnicodeEncodeError:
            continue
        size = len(message.encode("utf-8"))
        if total + size > MAX_MESSAGE_BYTES_TOTAL:
            break
        total += size
        priority = record.get("PRIORITY")
        severity = (
            _SEVERITIES[int(priority)]
            if isinstance(priority, str) and len(priority) == 1 and priority in "01234567"
            else None
        )
        entries.append(
            {
                "entry_id": digest,
                "occurred_at": _occurred_at(record.get("__REALTIME_TIMESTAMP")),
                "severity": severity,
                "message": message,
            }
        )
    return entries[-MAX_UPLOAD_ENTRIES:]


class JournalCollector:
    def __init__(self, process: BoundedProcess | None = None) -> None:
        self.process = process or BoundedProcess()

    async def collect(self, source: str) -> dict[str, Any]:
        if source not in SOURCES:
            raise ValueError("Unsupported Log Watch source.")
        args = [
            "/usr/bin/journalctl",
            "--system",
            "--no-pager",
            "--output=json",
            "--since=-5min",
            "--lines=100",
        ]
        if source == "skybeat_agent":
            args.extend(("--unit=skybeat-agent.service",))
        elif source == "kernel":
            args.append("--dmesg")
        try:
            result = await self.process.run(args, 4.0)
        except OSError:
            status = "collection_error"
            entries: list[dict[str, Any]] = []
        else:
            permission = (
                b"permission" in result.error.lower() or b"access denied" in result.error.lower()
            )
            if result.reason == "permission_denied" or permission:
                status, entries = "permission_unavailable", []
            elif result.reason:
                status, entries = "collection_error", []
            else:
                status, entries = "available", parse_journal(result.output)
        return {"schema_version": 1, "source": source, "status": status, "entries": entries}

    async def close(self) -> None:
        await self.process.close()
