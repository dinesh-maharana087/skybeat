"""Structured logs with bounded, explicitly selected context and secret redaction."""

import json
import logging
import re
from datetime import UTC, datetime


class SafeJSONFormatter(logging.Formatter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets = [secret for secret in secrets or [] if secret]

    def redact(self, value: str) -> str:
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"sb1\.[A-Za-z0-9-]+\.[A-Za-z0-9_-]+", "[REDACTED]", value)
        value = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value)
        value = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", value)
        value = re.sub(
            r"(?i)((?:password|secret|token|authorization|cookie)\s*[:=]\s*)[^\s,;]+",
            r"\1[REDACTED]",
            value,
        )
        return value[:2048]

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "message": self.redact(record.getMessage()),
        }
        for key in ("request_id", "device_id", "event_type", "error_category"):
            value = getattr(record, key, None)
            if isinstance(value, str):
                payload[key] = self.redact(value)
        if record.exc_info and record.exc_info[0]:
            payload["error_category"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str, secrets: list[str]) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJSONFormatter(secrets))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorn installs independent handlers before loading the app factory.
    # Its error logger sees exceptions re-raised by Starlette after a safe 500.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.setLevel(logging.NOTSET)
        logger.propagate = True
        logger.disabled = False
    # Default access records contain complete query strings, including OAuth
    # codes and state. Only explicitly safe application request logs are used.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False
    access_logger.disabled = True
    # Never emit SQL values or request URLs through library debug output.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
