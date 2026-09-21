import json
import logging

from app.logging import SafeJSONFormatter


def test_logging_redacts_sensitive_values_and_does_not_render_exception_text():
    formatter = SafeJSONFormatter(secrets=["super-secret-value"])
    try:
        raise ValueError("super-secret-value")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "skybeat", logging.ERROR, __file__, 1,
            "connection failed: %s", ("mysql+pymysql://user:password@localhost/db",),
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
    record = logging.LogRecord("skybeat", logging.INFO, __file__, 1, f"failed {token}\ninjected", (), None)
    rendered = SafeJSONFormatter().format(record)
    assert token not in rendered
    assert "\n" not in rendered
    assert json.loads(rendered)["level"] == "INFO"
