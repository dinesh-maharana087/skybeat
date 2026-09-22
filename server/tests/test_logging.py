import json
import logging
import logging.config

import pytest
from uvicorn.config import LOGGING_CONFIG

from app.logging import SafeJSONFormatter, configure_logging


@pytest.fixture
def configure_uvicorn_logging():
    loggers = [
        logging.getLogger(name)
        for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine", "httpx")
    ]
    original = [
        (logger, logger.handlers[:], logger.level, logger.propagate, logger.disabled)
        for logger in loggers
    ]

    def configure():
        logging.config.dictConfig(LOGGING_CONFIG)
        configure_logging("INFO", [])

    try:
        yield configure
    finally:
        for logger, handlers, level, propagate, disabled in original:
            logger.handlers = handlers
            logger.setLevel(level)
            logger.propagate = propagate
            logger.disabled = disabled


def test_logging_redacts_sensitive_values_and_does_not_render_exception_text():
    formatter = SafeJSONFormatter(secrets=["super-secret-value"])
    try:
        raise ValueError("super-secret-value")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "skybeat",
            logging.ERROR,
            __file__,
            1,
            "connection failed: %s",
            ("mysql+pymysql://user:password@localhost/db",),
            sys.exc_info(),
        )
    record.authorization = "Bearer super-secret-value"
    rendered = formatter.format(record)
    assert "password" not in rendered
    assert "super-secret-value" not in rendered
    payload = json.loads(rendered)
    assert payload["error_category"] == "ValueError"
    assert "traceback" not in payload
    assert "authorization" not in payload


def test_logging_redacts_device_tokens_and_line_breaks():
    token = "sb1.550e8400-e29b-41d4-a716-446655440000." + "a" * 43
    record = logging.LogRecord(
        "skybeat", logging.INFO, __file__, 1, f"failed {token}\ninjected", (), None
    )
    rendered = SafeJSONFormatter().format(record)
    assert token not in rendered
    assert "\n" not in rendered
    assert json.loads(rendered)["level"] == "INFO"


def test_uvicorn_exception_logging_uses_safe_formatter(configure_uvicorn_logging, capsys):
    configure_uvicorn_logging()
    try:
        raise RuntimeError("unexpected-sensitive-exception-text")
    except RuntimeError:
        logging.getLogger("uvicorn.error").error("Exception in ASGI application", exc_info=True)

    captured = capsys.readouterr()
    assert "unexpected-sensitive-exception-text" not in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""
    records = [json.loads(line) for line in captured.err.splitlines()]
    assert len(records) == 1
    assert records[0]["component"] == "uvicorn.error"
    assert records[0]["error_category"] == "RuntimeError"


def test_uvicorn_access_logging_cannot_expose_oauth_query(configure_uvicorn_logging, capsys):
    configure_uvicorn_logging()
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:12345",
        "GET",
        "/auth/google/callback?code=private-authorization-code&state=private-state",
        "1.1",
        302,
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
