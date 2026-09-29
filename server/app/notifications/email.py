"""Bounded SMTP email provider with normalized, secret-safe outcomes."""

import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape

from app.notifications.types import DeliveryMessage, ProviderOutcome, ProviderResult


def _safe_text(value: str) -> str:
    return "".join(
        character if character >= " " and character != "\x7f" else " " for character in value
    )


def _display_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%d %b %Y, %H:%M UTC")


def _duration_label(started_at: datetime, ended_at: datetime) -> str | None:
    seconds = int((ended_at - started_at).total_seconds())
    if seconds <= 0:
        return None
    total_minutes = seconds // 60
    if total_minutes == 0:
        return "less than a minute"
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        return f"{minutes} minute" + ("" if minutes == 1 else "s")
    hour_label = f"{hours} hour" + ("" if hours == 1 else "s")
    if minutes == 0:
        return hour_label
    return f"{hour_label} {minutes} minute" + ("" if minutes == 1 else "s")


@dataclass(frozen=True)
class _OperationalEmailContent:
    subject: str
    heading: str
    summary: str
    details: tuple[tuple[str, str], ...]
    explanation: tuple[str, ...]
    next_steps_title: str
    next_steps: tuple[str, ...]
    follow_up: str | None


def _offline_content(
    delivery: DeliveryMessage, *, project: str, device: str
) -> _OperationalEmailContent:
    return _OperationalEmailContent(
        subject=f"[SkyBeat] Device Offline \N{EM DASH} {device}",
        heading="DEVICE OFFLINE",
        summary=(
            f"SkyBeat detected that {device} is no longer communicating with the monitoring server."
        ),
        details=(
            ("Status", "Offline"),
            ("Project", project),
            ("Device", device),
            ("Offline detected", _display_time(delivery.occurred_at)),
        ),
        explanation=(
            "SkyBeat has not received a valid heartbeat from the device for the configured "
            "offline threshold.",
            "SkyBeat cannot currently confirm that the device is reachable and reporting.",
            "It does not necessarily prove that the physical computer is powered off.",
            "Possible causes include power loss, network interruption, SkyBeat agent/service "
            "failure, operating-system/device failure, or other connectivity problems.",
        ),
        next_steps_title="Recommended checks",
        next_steps=(
            "Confirm the device has power.",
            "Confirm the device is reachable on the network.",
            "Check whether the SkyBeat agent/service is running.",
            "If the device is intentionally offline, no immediate action is required.",
        ),
        follow_up="SkyBeat will send another notification when communication is restored.",
    )


def _recovery_content(
    delivery: DeliveryMessage, *, project: str, device: str
) -> _OperationalEmailContent:
    details: list[tuple[str, str]] = [
        ("Status", "Communication Restored"),
        ("Project", project),
        ("Device", device),
        ("Offline since", _display_time(delivery.opened_at)),
        ("Recovered at", _display_time(delivery.occurred_at)),
    ]
    duration = _duration_label(delivery.opened_at, delivery.occurred_at)
    if duration is not None:
        details.append(("Offline duration", duration))
    return _OperationalEmailContent(
        subject=f"[SkyBeat] Communication Restored \N{EM DASH} {device}",
        heading="COMMUNICATION RESTORED",
        summary=(
            f"SkyBeat has resumed receiving valid heartbeats from {device} after an offline "
            "incident."
        ),
        details=tuple(details),
        explanation=(
            "The device had previously been marked offline because SkyBeat stopped receiving "
            "valid heartbeats. Communication has now resumed.",
            "This confirms that communication between the device and SkyBeat has been restored.",
            "It does not necessarily prove that every application/service on the device is "
            "healthy unless those checks are separately verified.",
        ),
        next_steps_title="Next steps",
        next_steps=(
            "No action is required if the interruption was expected.",
            "If the outage was unexpected, consider checking the device and network logs to "
            "understand the cause.",
        ),
        follow_up=None,
    )


def _gpu_degraded_content(
    delivery: DeliveryMessage, *, project: str, device: str
) -> _OperationalEmailContent:
    return _OperationalEmailContent(
        subject=f"[SkyBeat] GPU Degraded \N{EM DASH} {device}",
        heading="GPU DEGRADED",
        summary=f"SkyBeat confirmed a GPU health degradation on {device}.",
        details=(
            ("Status", "GPU Degraded"),
            ("Project", project),
            ("Device", device),
            ("Detected at", _display_time(delivery.occurred_at)),
        ),
        explanation=(
            "GPU health degradation was confirmed by two fresh observations.",
            "The current GPU state requires investigation.",
        ),
        next_steps_title="Recommended checks",
        next_steps=(
            "Check the device and GPU logs for the reported period.",
            "Confirm the NVIDIA driver and GPU monitoring tools are available.",
            "Review the device's current GPU health before taking corrective action.",
        ),
        follow_up=None,
    )


def _gpu_recovered_content(
    delivery: DeliveryMessage, *, project: str, device: str
) -> _OperationalEmailContent:
    return _OperationalEmailContent(
        subject=f"[SkyBeat] GPU Recovered \N{EM DASH} {device}",
        heading="GPU RECOVERED",
        summary=f"SkyBeat confirmed that GPU health has recovered on {device}.",
        details=(
            ("Status", "GPU Recovered"),
            ("Project", project),
            ("Device", device),
            ("Recovered at", _display_time(delivery.occurred_at)),
        ),
        explanation=(
            "GPU health recovery was confirmed by two fresh observations.",
            "The current GPU state is OK.",
        ),
        next_steps_title="Next steps",
        next_steps=(
            "No action is required if the recovery was expected.",
            "If the degradation was unexpected, review device and GPU logs for the cause.",
        ),
        follow_up=None,
    )


def _generic_content(
    delivery: DeliveryMessage, *, project: str, device: str
) -> _OperationalEmailContent:
    event_kind = _safe_text(delivery.event_kind)
    return _OperationalEmailContent(
        subject=f"[SkyBeat] Alert \N{EM DASH} {device}",
        heading="SKYBEAT ALERT",
        summary=f"SkyBeat recorded an operational notification for {device}.",
        details=(
            ("Status", "Alert"),
            ("Project", project),
            ("Device", device),
            ("Occurred at", _display_time(delivery.occurred_at)),
            ("Event kind", event_kind),
        ),
        explanation=(f"Unknown notification type: {event_kind}",),
        next_steps_title="Next steps",
        next_steps=("Review the incident reference and SkyBeat event history.",),
        follow_up=None,
    )


def _content_for(
    delivery: DeliveryMessage, *, project: str, device: str
) -> _OperationalEmailContent:
    builders = {
        "DEVICE_OFFLINE": _offline_content,
        "DEVICE_RECOVERED": _recovery_content,
        "GPU_DEGRADED": _gpu_degraded_content,
        "GPU_RECOVERED": _gpu_recovered_content,
    }
    builder = builders.get(delivery.event_kind)
    if builder is None:
        return _generic_content(delivery, project=project, device=device)
    return builder(delivery, project=project, device=device)


def _operational_plaintext(content: _OperationalEmailContent, incident_uuid: str) -> str:
    lines = ["SKYBEAT", "", content.heading, "", content.summary, "", "Details"]
    lines.extend(f"{label}: {value}" for label, value in content.details)
    lines.extend(("", "What SkyBeat knows", *content.explanation, "", content.next_steps_title))
    lines.extend(f"{index}. {step}" for index, step in enumerate(content.next_steps, start=1))
    if content.follow_up is not None:
        lines.extend(("", content.follow_up))
    lines.extend(
        (
            "",
            "Reference",
            f"Incident: {incident_uuid}",
            "",
            "This is an automated operational alert from SkyBeat.",
        )
    )
    return "\n".join(lines) + "\n"


def _operational_html(content: _OperationalEmailContent, incident_uuid: str) -> str:
    detail_rows = "".join(
        (
            "<tr>"
            '<th align="left" style="padding:8px 12px;border-bottom:1px solid #d9e2ec;'
            'color:#334e68;font-size:14px;font-weight:600;">'
            f"{escape(label)}</th>"
            '<td class="detail-value" align="left" style="padding:8px 12px;'
            'border-bottom:1px solid #d9e2ec;color:#102a43;font-size:14px;">'
            f"{escape(value)}</td>"
            "</tr>"
        )
        for label, value in content.details
    )
    explanation = "".join(
        f'<p style="margin:0 0 12px;color:#334e68;font-size:15px;line-height:22px;">'
        f"{escape(paragraph)}</p>"
        for paragraph in content.explanation
    )
    next_steps = "".join(
        f'<li style="margin:0 0 8px;color:#334e68;font-size:15px;line-height:22px;">'
        f"{escape(step)}</li>"
        for step in content.next_steps
    )
    follow_up = (
        ""
        if content.follow_up is None
        else (
            f'<p style="margin:0 0 20px;color:#334e68;font-size:15px;line-height:22px;">'
            f"{escape(content.follow_up)}</p>"
        )
    )
    return "".join(
        (
            '<!doctype html><html><body style="margin:0;padding:0;background:#f3f6fa;">',
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'border="0" style="border-collapse:collapse;background:#f3f6fa;">',
            '<tr><td align="center" style="padding:24px 12px;">',
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'border="0" style="max-width:640px;border-collapse:collapse;background:#ffffff;'
            'border:1px solid #d9e2ec;">',
            '<tr><td style="padding:28px;">',
            '<p style="margin:0 0 12px;color:#1f4f82;font-size:14px;font-weight:700;'
            'letter-spacing:0.08em;">SkyBeat</p>',
            f'<h1 style="margin:0 0 12px;color:#102a43;font-size:24px;line-height:30px;">'
            f"{escape(content.heading)}</h1>",
            f'<p style="margin:0 0 20px;color:#243b53;font-size:16px;line-height:24px;">'
            f"{escape(content.summary)}</p>",
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'border="0" style="border-collapse:collapse;border:1px solid #d9e2ec;'
            'margin:0 0 20px;">',
            detail_rows,
            "</table>",
            explanation,
            f'<h2 style="margin:20px 0 10px;color:#102a43;font-size:17px;line-height:22px;">'
            f"{escape(content.next_steps_title)}</h2>",
            '<ol style="margin:0 0 20px;padding-left:24px;">',
            next_steps,
            "</ol>",
            follow_up,
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'border="0" style="border-collapse:collapse;background:#f7fafc;">',
            '<tr><td style="padding:12px;">',
            '<p style="margin:0 0 4px;color:#486581;font-size:12px;font-weight:700;">Reference</p>',
            '<p style="margin:0;color:#486581;font-size:12px;line-height:18px;">'
            f"Incident: {escape(incident_uuid)}</p>",
            "</td></tr></table>",
            '<p style="margin:20px 0 0;color:#627d98;font-size:12px;line-height:18px;">'
            "This is an automated operational alert from SkyBeat.</p>",
            "</td></tr></table>",
            "</td></tr></table>",
            "</body></html>",
        )
    )


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
        incident_uuid = _safe_text(delivery.incident_uuid)
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = delivery.destination
        message["Message-ID"] = f"<{delivery.delivery_uuid}@skybeat>"
        content = _content_for(delivery, project=project, device=device)
        message["Subject"] = content.subject
        message.set_content(_operational_plaintext(content, incident_uuid))
        message.add_alternative(_operational_html(content, incident_uuid), subtype="html")
        return message
