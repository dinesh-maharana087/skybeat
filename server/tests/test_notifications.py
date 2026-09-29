import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest

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


def _render_message(delivery: DeliveryMessage):
    provider = SMTPEmailProvider(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        from_address="skybeat@example.test",
        timeout_seconds=15,
    )
    return provider._message(delivery)


class _EmailHTMLValidator(HTMLParser):
    _VOID_TAGS = frozenset({"br", "hr", "img", "meta"})

    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.text_locations: list[tuple[str, tuple[str, ...], bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self._VOID_TAGS:
            self.stack.append((tag, tag == "td" and ("class", "detail-value") in attrs))

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1][0] != tag:
            self.errors.append(f"unexpected closing tag: {tag}")
            return
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text_locations.append(
                (
                    data.strip(),
                    tuple(tag for tag, _is_detail in self.stack),
                    any(is_detail for _tag, is_detail in self.stack),
                )
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
    assert sent[0]["To"] == "ops@example.test"
    assert sent[0]["Subject"] == "[SkyBeat] Device Offline \N{EM DASH} GPU host 01"
    assert sent[0]["Message-ID"] == "<4a4c9d7f-3d7a-4a1f-8d6b-041a7d2ecce0@skybeat>"
    assert (
        "SkyBeat detected that GPU host 01 is no longer communicating with the monitoring server."
        in sent[0].get_body(preferencelist=("plain",)).get_content()
    )
    assert "<html>" in sent[0].get_body(preferencelist=("html",)).get_content()


def test_offline_rendering_explains_the_heartbeat_timeout_and_recommended_checks():
    message = _render_message(_message())

    plain = message.get_body(preferencelist=("plain",)).get_content()

    assert "DEVICE OFFLINE" in plain
    assert "Status: Offline" in plain
    assert "Project: Training Fleet" in plain
    assert "Device: GPU host 01" in plain
    assert "Offline detected: 23 Sep 2026, 12:03 UTC" in plain
    assert (
        "SkyBeat has not received a valid heartbeat from the device for the configured offline "
        "threshold." in plain
    )
    assert "It does not necessarily prove that the physical computer is powered off." in plain
    assert (
        "Possible causes include power loss, network interruption, SkyBeat agent/service failure, "
        "operating-system/device failure, or other connectivity problems." in plain
    )
    assert "1. Confirm the device has power." in plain
    assert "4. If the device is intentionally offline, no immediate action is required." in plain
    assert "SkyBeat will send another notification when communication is restored." in plain
    assert "Reference" in plain
    assert "Incident: 13ee3e3b-3fe4-4b93-97c5-1ea5527bd459" in plain
    assert "Last seen:" not in plain


def test_recovery_rendering_uses_communication_restored_and_human_duration():
    message = _render_message(_message("DEVICE_RECOVERED"))

    plain = message.get_body(preferencelist=("plain",)).get_content()

    assert message["Subject"] == ("[SkyBeat] Communication Restored \N{EM DASH} GPU host 01")
    assert "COMMUNICATION RESTORED" in plain
    assert "Status: Communication Restored" in plain
    assert (
        "SkyBeat has resumed receiving valid heartbeats from GPU host 01 after an offline incident."
        in plain
    )
    assert "Offline since: 23 Sep 2026, 12:00 UTC" in plain
    assert "Recovered at: 23 Sep 2026, 12:03 UTC" in plain
    assert "Offline duration: 3 minutes" in plain
    assert (
        "This confirms that communication between the device and SkyBeat has been restored."
        in plain
    )
    assert "No action is required if the interruption was expected." in plain
    assert "Reference" in plain
    assert plain.count("This is an automated operational alert from SkyBeat.") == 1


def test_recovery_rendering_omits_duration_when_incident_timestamps_are_invalid():
    delivery = replace(
        _message("DEVICE_RECOVERED"),
        opened_at=datetime(2026, 9, 23, 12, 4, tzinfo=UTC),
        closed_at=None,
    )

    plain = _render_message(delivery).get_body(preferencelist=("plain",)).get_content()

    assert "Offline duration:" not in plain
    assert "Duration:" not in plain


def test_html_email_uses_a_balanced_presentation_table_and_keeps_branding_out_of_details():
    delivery = replace(
        _message(),
        project_name="<Project & Co>",
        device_name="GPU <01>",
    )
    html = _render_message(delivery).get_body(preferencelist=("html",)).get_content()
    validator = _EmailHTMLValidator()
    validator.feed(html)
    validator.close()

    assert '<table role="presentation"' in html
    assert "&lt;Project &amp; Co&gt;" in html
    assert "GPU &lt;01&gt;" in html
    assert validator.errors == []
    assert validator.stack == []
    brand_locations = [
        (location, inside_detail_cell)
        for text, location, inside_detail_cell in validator.text_locations
        if text.casefold() == "skybeat"
    ]
    assert brand_locations
    assert all(not inside_detail_cell for _location, inside_detail_cell in brand_locations)


@pytest.mark.parametrize(
    ("event_kind", "subject", "heading", "event_specific_text"),
    (
        (
            "DEVICE_OFFLINE",
            "[SkyBeat] Device Offline \N{EM DASH} GPU host 01",
            "DEVICE OFFLINE",
            "SkyBeat has not received a valid heartbeat",
        ),
        (
            "DEVICE_RECOVERED",
            "[SkyBeat] Communication Restored \N{EM DASH} GPU host 01",
            "COMMUNICATION RESTORED",
            "Offline duration: 3 minutes",
        ),
        (
            "GPU_DEGRADED",
            "[SkyBeat] GPU Degraded \N{EM DASH} GPU host 01",
            "GPU DEGRADED",
            "GPU health degradation was confirmed by two fresh observations.",
        ),
        (
            "GPU_RECOVERED",
            "[SkyBeat] GPU Recovered \N{EM DASH} GPU host 01",
            "GPU RECOVERED",
            "GPU health recovery was confirmed by two fresh observations.",
        ),
    ),
)
def test_known_event_kinds_use_the_explicit_operational_renderer(
    event_kind, subject, heading, event_specific_text
):
    message = _render_message(_message(event_kind))
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()

    assert message["Subject"] == subject
    assert heading in plain
    assert event_specific_text in plain
    assert "detail-value" in html
    assert "SkyBeat: Device" not in html
    assert "Operational notification from SkyBeat." not in html
    assert "Device status is determined by server heartbeat receipt time." not in html


def test_unknown_event_kind_uses_the_safe_generic_operational_renderer():
    message = _render_message(_message("CUSTOM_EVENT"))
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()

    assert message["Subject"] == "[SkyBeat] Alert \N{EM DASH} GPU host 01"
    assert "SKYBEAT ALERT" in plain
    assert "Unknown notification type: CUSTOM_EVENT" in plain
    assert "detail-value" in html
    assert "Operational notification from SkyBeat." not in html


def test_preview_helper_writes_html_and_plaintext_for_each_supported_event(tmp_path):
    server_directory = Path(__file__).resolve().parents[1]
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and repository helper path
        (
            sys.executable,
            "tests/render_notification_previews.py",
            "--output-dir",
            str(tmp_path),
        ),
        cwd=server_directory,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert {path.name for path in tmp_path.iterdir()} == {
        "device-offline.html",
        "device-offline.txt",
        "device-recovered.html",
        "device-recovered.txt",
        "gpu-degraded.html",
        "gpu-degraded.txt",
        "gpu-recovered.html",
        "gpu-recovered.txt",
    }


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
    assert sent[0]["Subject"] == "[SkyBeat] GPU Degraded \N{EM DASH} GPU host 01"
    assert "two fresh observations" in sent[0].get_body(preferencelist=("plain",)).get_content()
