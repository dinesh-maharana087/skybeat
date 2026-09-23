"""Real-MySQL durable delivery and retry coverage."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import database_utc
from app.health.service import AvailabilityService
from app.models import Device, NotificationAttempt, NotificationDelivery
from app.notifications.service import NotificationService
from app.notifications.types import ProviderOutcome, ProviderResult

pytestmark = pytest.mark.mysql


class Provider:
    def __init__(self, result):
        self.result = result
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return self.result


def _offline_delivery(identity, mysql_database):
    project = identity.create_project("Delivery")
    enrolled = identity.enroll(project.public_id, "Email device")
    with mysql_database.transaction() as session:
        device = session.get(type(enrolled.device), enrolled.device.id)
        assert device is not None
        device.monitoring_started_at = database_utc(session) - timedelta(seconds=180)
    AvailabilityService(mysql_database, email_recipients=("ops@example.test",)).sweep()
    return enrolled


def test_delivery_worker_records_accepted_smtp_attempt(identity, mysql_database):
    _offline_delivery(identity, mysql_database)
    provider = Provider(ProviderResult(ProviderOutcome.ACCEPTED, provider_message_id="safe-id"))

    NotificationService(mysql_database, jitter=lambda _: 0).process_due(provider)

    with mysql_database.transaction() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery is not None
        assert delivery.status == "SUCCEEDED"
        assert delivery.attempt_count == 1
        assert delivery.provider_message_id == "safe-id"
        attempt = session.scalar(select(NotificationAttempt))
        assert attempt is not None
        assert attempt.outcome == "ACCEPTED"
    assert len(provider.messages) == 1


def test_transient_delivery_failure_is_retried_without_losing_attempt(identity, mysql_database):
    _offline_delivery(identity, mysql_database)
    provider = Provider(ProviderResult(ProviderOutcome.TRANSIENT_FAILURE, "smtp_unavailable"))

    NotificationService(mysql_database, jitter=lambda _: 0).process_due(provider)

    with mysql_database.transaction() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery is not None
        assert delivery.status == "RETRY_WAIT"
        assert delivery.attempt_count == 1
        assert delivery.next_attempt_at is not None
        assert delivery.last_error_category == "smtp_unavailable"
        attempt = session.scalar(select(NotificationAttempt))
        assert attempt is not None
        assert attempt.outcome == "TRANSIENT_FAILURE"


def test_worker_restart_recovers_expired_in_progress_claim(identity, mysql_database):
    _offline_delivery(identity, mysql_database)
    service = NotificationService(mysql_database, jitter=lambda _: 0)
    claims = service.claim_due()
    assert len(claims) == 1
    with mysql_database.transaction() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery is not None
        delivery.lease_expires_at = database_utc(session) - timedelta(seconds=1)

    service.recover_stuck()

    with mysql_database.transaction() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery is not None
        assert delivery.status == "RETRY_WAIT"
        assert delivery.attempt_count == 1
        attempt = session.scalar(select(NotificationAttempt))
        assert attempt is not None
        assert attempt.outcome == "UNCERTAIN"
        assert attempt.error_category == "worker_crash"


def test_recovery_finishes_inflight_outage_attempt_without_permitting_retry(
    identity, mysql_database
):
    enrolled = _offline_delivery(identity, mysql_database)
    notifications = NotificationService(mysql_database, jitter=lambda _: 0)
    claim = notifications.claim_due()[0]
    with mysql_database.transaction() as session:
        device = session.scalar(
            select(Device).where(Device.id == enrolled.device.id).with_for_update()
        )
        assert device is not None
        AvailabilityService(mysql_database).accept_heartbeat(session, device, database_utc(session))

    notifications.record_result(
        claim, ProviderResult(ProviderOutcome.TRANSIENT_FAILURE, "smtp_unavailable")
    )

    with mysql_database.transaction() as session:
        delivery = session.scalar(select(NotificationDelivery))
        assert delivery is not None
        assert delivery.status == "CANCELLED"
        assert delivery.cancel_reason == "superseded_by_recovery"
        attempt = session.scalar(select(NotificationAttempt))
        assert attempt is not None
        assert attempt.outcome == "TRANSIENT_FAILURE"


def test_email_and_sms_deliveries_are_claimed_and_retried_independently(identity, mysql_database):
    project = identity.create_project("Channel independence")
    enrolled = identity.enroll(project.public_id, "Dual channel device")
    with mysql_database.transaction() as session:
        device = session.get(Device, enrolled.device.id)
        assert device is not None
        device.monitoring_started_at = database_utc(session) - timedelta(seconds=180)
    AvailabilityService(
        mysql_database,
        email_recipients=("ops@example.test",),
        sms_recipients=("+15551234567",),
    ).sweep()
    email = Provider(ProviderResult(ProviderOutcome.ACCEPTED, provider_message_id="email-id"))
    sms = Provider(ProviderResult(ProviderOutcome.TRANSIENT_FAILURE, "sms_timeout"))

    NotificationService(mysql_database, jitter=lambda _: 0).process_due(
        {"EMAIL": email, "SMS": sms}
    )

    with mysql_database.transaction() as session:
        deliveries = {
            delivery.channel: delivery for delivery in session.scalars(select(NotificationDelivery))
        }
        assert deliveries["EMAIL"].status == "SUCCEEDED"
        assert deliveries["EMAIL"].provider_message_id == "email-id"
        assert deliveries["SMS"].status == "RETRY_WAIT"
        assert deliveries["SMS"].last_error_category == "sms_timeout"
    assert len(email.messages) == len(sms.messages) == 1
    assert sms.messages[0].delivery_uuid
