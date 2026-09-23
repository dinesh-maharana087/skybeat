"""Independent Stage 03 health and notification worker entry point."""

import logging
import signal
from collections.abc import Callable
from threading import Event
from time import monotonic

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
    _sweep(settings, database)
    _deliver(settings, database, provider)


def _sweep(settings: Settings, database: Database) -> None:
    AvailabilityService(
        database,
        email_recipients=settings.alert_email_recipients,
        sms_recipients=settings.alert_sms_recipients if settings.sms_enabled else (),
        suspect_after_seconds=settings.suspect_after_seconds,
        offline_after_seconds=settings.offline_after_seconds,
    ).sweep()


def _deliver(
    settings: Settings,
    database: Database,
    provider: NotificationProvider | dict[str, NotificationProvider] | None,
) -> None:
    if provider is not None:
        NotificationService(database).process_due(provider, limit=settings.notification_concurrency)


def run_loop(
    settings: Settings,
    database: Database,
    providers: NotificationProvider | dict[str, NotificationProvider] | None,
    stop: Event,
    *,
    monotonic: Callable[[], float] = monotonic,
    wait: Callable[[float], bool] | None = None,
) -> None:
    """Schedule bounded health and notification work independently until shutdown."""
    wait_for = wait or stop.wait
    next_sweep_at = 0.0
    next_delivery_at = 0.0
    while not stop.is_set():
        now = monotonic()
        if now >= next_sweep_at:
            _sweep(settings, database)
            next_sweep_at = now + settings.health_sweep_seconds
        if now >= next_delivery_at:
            _deliver(settings, database, providers)
            next_delivery_at = now + settings.notification_poll_seconds
        wait_for(max(0.0, min(next_sweep_at, next_delivery_at) - monotonic()))


def main() -> None:
    settings = Settings()
    database = Database(settings)
    providers = build_notification_providers(settings)
    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        logger.info("Worker stopping", extra={"event_type": "shutdown"})
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
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
        logger.info("Worker started", extra={"event_type": "startup"})
        run_loop(settings, database, providers, stop)
    finally:
        database.dispose()
        logger.info("Worker stopped", extra={"event_type": "shutdown"})


if __name__ == "__main__":
    main()
