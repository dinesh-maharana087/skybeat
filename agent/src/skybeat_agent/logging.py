"""Small structured, secret-safe agent logging boundary."""

import logging
import re
from collections.abc import Iterable
from typing import Any

_BASE_RECORD_FACTORY = logging.getLogRecordFactory()
_configured_secrets: tuple[str, ...] = ()
_BEARER_PATTERN = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+")
_SKYBEAT_TOKEN_PATTERN = re.compile(r"\bsb1\.[A-Za-z0-9-]+\.[A-Za-z0-9_-]+\b")
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?ix)"
    r"(?P<key>[a-z0-9_.-]*(?:token|secret|password|api[_-]?key)[a-z0-9_.-]*)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<quote>['\"]?)"
    r"(?P<value>[^\s,;}\]]+)"
    r"(?P=quote)"
)


def _redact(text: str) -> str:
    redacted = text
    for secret in _configured_secrets:
        redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _BEARER_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _SKYBEAT_TOKEN_PATTERN.sub("[REDACTED]", redacted)
    return _SENSITIVE_VALUE_PATTERN.sub(
        lambda match: (
            f"{match.group('key')}{match.group('separator')}"
            f"{match.group('quote')}[REDACTED]{match.group('quote')}"
        ),
        redacted,
    )


def _redacting_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _BASE_RECORD_FACTORY(*args, **kwargs)
    try:
        message = record.getMessage()
    except Exception:
        message = "unrenderable_log_message"
    record.msg = _redact(message)
    record.args = ()
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    return record


def configure_logging(level: str, *, secrets: Iterable[str] = ()) -> None:
    """Configure process-wide logging with a mandatory safe-record boundary."""
    global _configured_secrets
    _configured_secrets = tuple(
        sorted((secret for secret in secrets if secret), key=len, reverse=True)
    )
    logging.setLogRecordFactory(_redacting_record_factory)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger().setLevel(level)
