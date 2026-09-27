"""Bounded SMTP email provider with normalized, secret-safe outcomes."""

import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape

from app.notifications.types import DeliveryMessage, ProviderOutcome, ProviderResult


def _safe_text(value: str) -> str:
    return "".join(
        character if character >= " " and character != "\x7f" else " " for character in value
    )


def _wire_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%d-%b-%Y %H:%M UTC")


class SMTPEmailProvider:
    """Send one operational email with a bounded SMTP exchange."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_address: str,
        timeout_seconds: int,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.timeout_seconds = timeout_seconds

    def send(self, delivery: DeliveryMessage) -> ProviderResult:
        message = self._message(delivery)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as client:
                client.starttls(context=ssl.create_default_context())
                if self.username is not None:
                    if self.password is None:
                        return ProviderResult(
                            ProviderOutcome.PERMANENT_FAILURE, "smtp_configuration"
                        )
                    client.login(self.username, self.password)
                refused = client.send_message(message)
                if refused:
                    return ProviderResult(
                        ProviderOutcome.PERMANENT_FAILURE, "smtp_recipient_rejected"
                    )
        except smtplib.SMTPAuthenticationError:
            return ProviderResult(ProviderOutcome.PERMANENT_FAILURE, "smtp_authentication")
        except smtplib.SMTPRecipientsRefused:
            return ProviderResult(ProviderOutcome.PERMANENT_FAILURE, "smtp_recipient_rejected")
        except smtplib.SMTPResponseException as error:
            category = "smtp_temporary" if 400 <= error.smtp_code < 500 else "smtp_rejected"
            outcome = (
                ProviderOutcome.TRANSIENT_FAILURE
                if category == "smtp_temporary"
                else ProviderOutcome.PERMANENT_FAILURE
            )
            return ProviderResult(outcome, category)
        except (OSError, TimeoutError, smtplib.SMTPServerDisconnected):
            return ProviderResult(ProviderOutcome.TRANSIENT_FAILURE, "smtp_unavailable")
        except smtplib.SMTPException:
            return ProviderResult(ProviderOutcome.UNCERTAIN, "smtp_protocol")
        except ValueError:
            return ProviderResult(ProviderOutcome.PERMANENT_FAILURE, "smtp_message_invalid")
        return ProviderResult(ProviderOutcome.ACCEPTED)

    def _message(self, delivery: DeliveryMessage) -> EmailMessage:
        project = _safe_text(delivery.project_name)
        device = _safe_text(delivery.device_name)
        event = {
            "DEVICE_OFFLINE": "OFFLINE",
            "DEVICE_RECOVERED": "RECOVERED",
            "GPU_DEGRADED": "GPU DEGRADED",
            "GPU_RECOVERED": "GPU RECOVERED",
        }.get(delivery.event_kind, "ALERT")
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = delivery.destination
        message["Subject"] = f"[SkyBeat] {event} - {project} / {device}"
        message["Message-ID"] = f"<{delivery.delivery_uuid}@skybeat>"
        body = [
            f"Project: {project}",
            f"Device: {device}",
            f"Event: {event}",
            f"Incident: {delivery.incident_uuid}",
        ]
        if event == "OFFLINE":
            body.extend(
                (
                    "Device is unreachable by the monitoring system.",
                    f"Offline threshold reached: {_wire_time(delivery.occurred_at)}",
                    "Current state: OFFLINE",
                )
            )
        elif event == "RECOVERED":
            duration = delivery.occurred_at - delivery.opened_at
            body.extend(
                (
                    f"Offline since: {_wire_time(delivery.opened_at)}",
                    f"Recovered: {_wire_time(delivery.occurred_at)}",
                    f"Duration: {int(duration.total_seconds())} seconds",
                    "Current state: ONLINE",
                )
            )
        elif event == "GPU DEGRADED":
            body.extend(
                (
                    "GPU health degradation was confirmed by two fresh observations.",
                    f"Detected: {_wire_time(delivery.occurred_at)}",
                    "Current GPU state requires investigation.",
                )
            )
        elif event == "GPU RECOVERED":
            body.extend(
                (
                    "GPU health recovery was confirmed by two fresh observations.",
                    f"Recovered: {_wire_time(delivery.occurred_at)}",
                    "Current GPU state: OK",
                )
            )
        else:
            body.append(f"Occurred: {_wire_time(delivery.occurred_at)}")
        text = "\n".join(body) + "\n"
        message.set_content(text)
        title = f"SkyBeat: Device {event.title()}"
        rows = "".join(
            f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
            for label, value in (
                ("Project", project),
                ("Device", device),
                ("Event", event),
                ("Incident", delivery.incident_uuid),
                ("Occurred", _wire_time(delivery.occurred_at)),
            )
        )
        html = "".join(
            (
                '<!doctype html><html><body style="margin:0;background:#f3f6fa;">',
                '<main style="max-width:640px;margin:24px auto;background:#fff;padding:28px;">',
                '<p style="margin:0;color:#4361ee;font-weight:700">SKYBEAT</p>',
                f'<h1 style="margin:12px 0">{escape(title)}</h1>',
                "<p>Operational notification from SkyBeat.</p>",
                '<table style="border-collapse:collapse;width:100%">',
                rows,
                "</table>",
                '<p style="color:#5d6b82">',
                "Device status is determined by server heartbeat receipt time.",
                "</p></main></body></html>",
            )
        )
        message.add_alternative(html, subtype="html")
        return message
