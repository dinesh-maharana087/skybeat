"""Bounded SMTP email provider with normalized, secret-safe outcomes."""

import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage

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
        event = "RECOVERED" if delivery.event_kind == "DEVICE_RECOVERED" else "OFFLINE"
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
        else:
            duration = delivery.occurred_at - delivery.opened_at
            body.extend(
                (
                    f"Offline since: {_wire_time(delivery.opened_at)}",
                    f"Recovered: {_wire_time(delivery.occurred_at)}",
                    f"Duration: {int(duration.total_seconds())} seconds",
                    "Current state: ONLINE",
                )
            )
        message.set_content("\n".join(body) + "\n")
        return message
