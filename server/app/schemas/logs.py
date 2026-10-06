"""Strict, bounded Log Watch upload contract."""

import json
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_LOG_BODY_BYTES = 72 * 1024
MAX_LOG_ENTRIES = 80
MAX_LOG_MESSAGE_CHARS = 2048
LOG_SOURCES = ("skybeat_agent", "system_journal", "kernel")
LogSourceName = Literal["skybeat_agent", "system_journal", "kernel"]
LogSourceStatus = Literal["available", "permission_unavailable", "collection_error"]
LogSeverity = Literal[
    "emergency", "alert", "critical", "error", "warning", "notice", "info", "debug"
]


class LogEntryUpload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    entry_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurred_at: datetime | None = None
    severity: LogSeverity | None = None
    message: str = Field(min_length=1, max_length=MAX_LOG_MESSAGE_CHARS)

    @field_validator("occurred_at", mode="before")
    @classmethod
    def aware_time(cls, value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("Timestamp must include a timezone.")
            return value
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value
        ):
            raise ValueError("Timestamp must be RFC 3339 with a timezone.")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Timestamp is invalid.") from None

    @field_validator("message")
    @classmethod
    def safe_text(cls, value: str) -> str:
        if any(
            ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF
            for char in value
        ):
            raise ValueError("Log message contains invalid characters.")
        return value


class LogUpload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    source: LogSourceName
    status: LogSourceStatus
    entries: list[LogEntryUpload] = Field(max_length=MAX_LOG_ENTRIES)


class LogUploadInvalid(ValueError):
    pass


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LogUploadInvalid("Duplicate JSON field.")
        result[key] = value
    return result


def parse_log_upload(raw: bytes) -> LogUpload:
    if len(raw) > MAX_LOG_BODY_BYTES:
        raise LogUploadInvalid("Payload is too large.")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(LogUploadInvalid("Invalid number.")),
        )
        if not isinstance(value, dict):
            raise LogUploadInvalid("Payload must be an object.")
        upload = LogUpload.model_validate(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, RecursionError):
        raise LogUploadInvalid("Log upload is invalid.") from None
    if upload.status != "available" and upload.entries:
        raise LogUploadInvalid("Unavailable source cannot include entries.")
    return upload
