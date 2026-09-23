"""Independent Stage 03 health and notification worker entry point."""

import logging
from time import sleep

from app.config import Settings
from app.db import Database
from app.health.service import AvailabilityService
from app.notifications.email import SMTPEmailProvider
from app.notifications.service import NotificationProvider, NotificationService
from app.notifications.sms import DisabledSMSProvider

logger = logging.getLogger(__name__)


def build_smtp_provider(settings: Settings) -> SMTPEmailProvider | None:
    """Build SMTP only when its non-secret routing configuration is complete."""
    if not settings.smtp_host or not settings.smtp_from_address:
        return None
    password = settings.smtp_password.get_secret_value() if settings.smtp_password else None
    return SMTPEmailProvider(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=password,
        from_address=settings.smtp_from_address,
        timeout_seconds=15,
    )


def build_notification_providers(settings: Settings) -> dict[str, NotificationProvider]:
    """Return independently routable providers; SMS remains deliberately vendor-neutral."""
    providers: dict[str, NotificationProvider] = {}
    email = build_smtp_provider(settings)
    if email is not None:
        providers["EMAIL"] = email
    if settings.sms_enabled and settings.alert_sms_recipients:
        providers["SMS"] = DisabledSMSProvider()
    return providers


def run_once(
    settings: Settings,
    database: Database,
    *,
    provider: NotificationProvider | dict[str, NotificationProvider] | None,
) -> None:
    """Perform one bounded sweep and then attempt a bounded notification batch."""
    AvailabilityService(
        database,
        email_recipients=settings.alert_email_recipients,
        sms_recipients=settings.alert_sms_recipients if settings.sms_enabled else (),
    ).sweep()
    if provider is not None:
        NotificationService(database).process_due(provider, limit=settings.notification_concurrency)


def main() -> None:
    settings = Settings()
    database = Database(settings)
    providers = build_notification_providers(settings)
    if settings.alert_email_recipients and "EMAIL" not in providers:
        logger.error(
            "Email recipients configured without usable SMTP provider",
            extra={"event_type": "notification_configuration", "error_category": "smtp_missing"},
        )
    if settings.sms_enabled and settings.alert_sms_recipients:
        logger.warning(
            "SMS recipients configured without a production SMS adapter",
            extra={
                "event_type": "notification_configuration",
                "error_category": "sms_not_configured",
            },
        )
    try:
        while True:
            run_once(settings, database, provider=providers)
            sleep(settings.health_sweep_seconds)
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
