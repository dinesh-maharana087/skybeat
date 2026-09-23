"""Independent Stage 03 health and notification worker entry point."""

import logging
from time import sleep

from app.config import Settings
from app.db import Database
from app.health.service import AvailabilityService
from app.notifications.email import SMTPEmailProvider
from app.notifications.service import NotificationProvider, NotificationService

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


def run_once(
    settings: Settings, database: Database, *, provider: NotificationProvider | None
) -> None:
    """Perform one bounded sweep and then attempt a bounded notification batch."""
    AvailabilityService(database, email_recipients=settings.alert_email_recipients).sweep()
    if provider is not None:
        NotificationService(database).process_due(provider, limit=settings.notification_concurrency)


def main() -> None:
    settings = Settings()
    database = Database(settings)
    provider = build_smtp_provider(settings)
    if settings.alert_email_recipients and provider is None:
        logger.error(
            "Email recipients configured without usable SMTP provider",
            extra={"event_type": "notification_configuration", "error_category": "smtp_missing"},
        )
    try:
        while True:
            run_once(settings, database, provider=provider)
            sleep(settings.health_sweep_seconds)
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
