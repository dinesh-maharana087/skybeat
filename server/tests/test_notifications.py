from datetime import UTC, datetime

from app.config import Settings
from app.notifications.email import SMTPEmailProvider
from app.notifications.types import DeliveryMessage, ProviderOutcome
from app.worker import build_smtp_provider


def _message(kind="DEVICE_OFFLINE"):
    return DeliveryMessage(
        delivery_uuid="4a4c9d7f-3d7a-4a1f-8d6b-041a7d2ecce0",
        destination="ops@example.test",
        event_kind=kind,
        project_name="Training Fleet",
        device_name="GPU host 01",
        incident_uuid="13ee3e3b-3fe4-4b93-97c5-1ea5527bd459",
        occurred_at=datetime(2026, 9, 23, 12, 3, tzinfo=UTC),
        opened_at=datetime(2026, 9, 23, 12, 0, tzinfo=UTC),
        closed_at=datetime(2026, 9, 23, 12, 3, tzinfo=UTC),
    )


def test_smtp_provider_sends_safe_offline_message_with_stable_message_id(monkeypatch):
    sent = []
    calls = []

    class SMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.test", 587, 15)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self, context):
            assert context is not None
            calls.append("starttls")

        def login(self, username, password):
            assert (username, password) == ("skybeat", "not-logged")
            calls.append("login")

        def send_message(self, message):
            sent.append(message)
            calls.append("send_message")
            return {}

    monkeypatch.setattr("app.notifications.email.smtplib.SMTP", SMTP)
    provider = SMTPEmailProvider(
        host="smtp.example.test",
        port=587,
        username="skybeat",
        password="not-logged",
        from_address="skybeat@example.test",
        timeout_seconds=15,
    )

    result = provider.send(_message())

    assert result.outcome is ProviderOutcome.ACCEPTED
    assert calls == ["starttls", "login", "send_message"]
    assert sent[0]["Subject"] == "[SkyBeat] OFFLINE - Training Fleet / GPU host 01"
    assert sent[0]["Message-ID"] == "<4a4c9d7f-3d7a-4a1f-8d6b-041a7d2ecce0@skybeat>"
    assert (
        "Device is unreachable by the monitoring system."
        in sent[0].get_body(preferencelist=("plain",)).get_content()
    )
    assert "<html>" in sent[0].get_body(preferencelist=("html",)).get_content()


def test_smtp_client_receives_an_unwrapped_settings_password_only_after_starttls(monkeypatch):
    calls = []

    class SMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self, context):
            assert context is not None
            calls.append("starttls")

        def login(self, username, password):
            assert (username, password) == ("skybeat", "secret-not-to-log")
            assert type(password) is str
            calls.append("login")

        def send_message(self, _message):
            calls.append("send_message")
            return {}

    monkeypatch.setattr("app.notifications.email.smtplib.SMTP", SMTP)
    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test",
        smtp_host="smtp.example.test",
        smtp_from_address="skybeat@example.test",
        smtp_username="skybeat",
        smtp_password="secret-not-to-log",
    )
    provider = build_smtp_provider(settings)

    assert provider is not None
    assert provider.send(_message()).outcome is ProviderOutcome.ACCEPTED
    assert calls == ["starttls", "login", "send_message"]


def test_smtp_authentication_failure_is_permanent_without_exposing_provider_text(
    monkeypatch, capsys
):
    import smtplib

    class SMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.test", 587, 15)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self, context):
            assert context is not None

        def login(self, *_):
            raise smtplib.SMTPAuthenticationError(
                535, b"sensitive provider detail secret-not-to-log"
            )

    monkeypatch.setattr("app.notifications.email.smtplib.SMTP", SMTP)
    provider = SMTPEmailProvider(
        host="smtp.example.test",
        port=587,
        username="skybeat",
        password="not-logged",
        from_address="skybeat@example.test",
        timeout_seconds=15,
    )

    result = provider.send(_message())

    assert result.outcome is ProviderOutcome.PERMANENT_FAILURE
    assert result.error_category == "smtp_authentication"
    captured = capsys.readouterr()
    assert "secret-not-to-log" not in captured.out + captured.err
    assert "sensitive provider detail" not in captured.out + captured.err


def test_smtp_timeout_is_retryable_without_provider_detail(monkeypatch):
    class SMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.test", 587, 15)
            raise TimeoutError("sensitive provider detail")

    monkeypatch.setattr("app.notifications.email.smtplib.SMTP", SMTP)
    provider = SMTPEmailProvider(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        from_address="skybeat@example.test",
        timeout_seconds=15,
    )

    result = provider.send(_message())

    assert result.outcome is ProviderOutcome.TRANSIENT_FAILURE
    assert result.error_category == "smtp_unavailable"


def test_smtp_provider_uses_gpu_specific_operational_content(monkeypatch):
    sent = []

    class SMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self, context):
            assert context is not None

        def send_message(self, message):
            sent.append(message)
            return {}

    monkeypatch.setattr("app.notifications.email.smtplib.SMTP", SMTP)
    provider = SMTPEmailProvider(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        from_address="skybeat@example.test",
        timeout_seconds=15,
    )

    assert provider.send(_message("GPU_DEGRADED")).outcome is ProviderOutcome.ACCEPTED
    assert sent[0]["Subject"] == "[SkyBeat] GPU DEGRADED - Training Fleet / GPU host 01"
    assert "two fresh observations" in sent[0].get_body(preferencelist=("plain",)).get_content()
