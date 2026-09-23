"""Durable MySQL notification claiming, attempts, and bounded retry state."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import SystemRandom
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Database, database_utc
from app.models import AlertEvent, Incident, NotificationAttempt, NotificationDelivery
from app.notifications.types import DeliveryMessage, ProviderOutcome, ProviderResult

logger = logging.getLogger(__name__)
_jitter_random = SystemRandom()

MAX_ATTEMPTS = 5
LEASE_SECONDS = 60
RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 15 * 60


class NotificationProvider(Protocol):
    def send(self, message: DeliveryMessage) -> ProviderResult: ...


@dataclass(frozen=True)
class ClaimedDelivery:
    delivery_id: int
    attempt_no: int
    lease_token: str
    message: DeliveryMessage


class NotificationService:
    """Claim jobs in short transactions; provider calls happen only after commit."""

    def __init__(
        self, database: Database, *, jitter: Callable[[float], float] | None = None
    ) -> None:
        self.database = database
        self.jitter = jitter or (lambda delay: _jitter_random.uniform(0, delay * 0.1))

    def process_due(self, provider: NotificationProvider, *, limit: int = 4) -> None:
        self.recover_stuck()
        for claim in self.claim_due(limit=limit):
            try:
                result = provider.send(claim.message)
            except Exception:
                logger.warning(
                    "Notification provider raised unexpectedly",
                    extra={
                        "event_type": "notification_provider_failure",
                        "error_category": "provider_exception",
                    },
                )
                result = ProviderResult(ProviderOutcome.UNCERTAIN, "provider_exception")
            self.record_result(claim, result)

    def claim_due(self, *, limit: int = 4) -> list[ClaimedDelivery]:
        if not 1 <= limit <= 4:
            raise ValueError("Notification claim limit is out of range.")
        with self.database.transaction() as session:
            now = database_utc(session)
            self._expire_unclaimed(session, now)
            rows = session.execute(
                select(NotificationDelivery, AlertEvent, Incident)
                .join(AlertEvent, NotificationDelivery.event_id == AlertEvent.id)
                .join(Incident, AlertEvent.incident_id == Incident.id)
                .where(
                    NotificationDelivery.status.in_(("PENDING", "RETRY_WAIT")),
                    NotificationDelivery.next_attempt_at <= now,
                    NotificationDelivery.expires_at > now,
                )
                .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            claims: list[ClaimedDelivery] = []
            for delivery, event, incident in rows:
                lease_token = str(uuid4())
                delivery.status = "IN_PROGRESS"
                delivery.attempt_count += 1
                delivery.lease_token = lease_token
                delivery.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
                delivery.updated_at = now
                session.add(
                    NotificationAttempt(
                        delivery_id=delivery.id,
                        attempt_no=delivery.attempt_count,
                        started_at=now,
                        finished_at=None,
                        outcome=None,
                        error_category=None,
                        provider_message_id=None,
                    )
                )
                claims.append(
                    ClaimedDelivery(
                        delivery_id=delivery.id,
                        attempt_no=delivery.attempt_count,
                        lease_token=lease_token,
                        message=DeliveryMessage(
                            delivery_uuid=delivery.delivery_uuid,
                            destination=delivery.destination_snapshot,
                            event_kind=event.event_kind,
                            project_name=event.project_name_snapshot,
                            device_name=event.device_name_snapshot,
                            incident_uuid=incident.incident_uuid,
                            occurred_at=event.occurred_at,
                            opened_at=incident.opened_at,
                            closed_at=incident.closed_at,
                        ),
                    )
                )
        return claims

    def record_result(self, claim: ClaimedDelivery, result: ProviderResult) -> None:
        with self.database.transaction() as session:
            delivery = session.scalar(
                select(NotificationDelivery)
                .where(NotificationDelivery.id == claim.delivery_id)
                .with_for_update()
            )
            if (
                delivery is None
                or delivery.status != "IN_PROGRESS"
                or delivery.lease_token != claim.lease_token
            ):
                return
            now = database_utc(session)
            attempt = session.scalar(
                select(NotificationAttempt).where(
                    NotificationAttempt.delivery_id == delivery.id,
                    NotificationAttempt.attempt_no == claim.attempt_no,
                )
            )
            if attempt is None:
                raise RuntimeError("Claimed notification attempt is missing.")
            attempt.finished_at = now
            attempt.outcome = result.outcome.value
            attempt.error_category = result.error_category
            attempt.provider_message_id = result.provider_message_id
            delivery.last_error_category = result.error_category
            delivery.provider_message_id = result.provider_message_id
            delivery.lease_token = None
            delivery.lease_expires_at = None
            delivery.updated_at = now
            if delivery.superseded_at is not None:
                delivery.status = "CANCELLED"
                delivery.next_attempt_at = None
            elif result.outcome is ProviderOutcome.ACCEPTED:
                delivery.status = "SUCCEEDED"
                delivery.next_attempt_at = None
            elif result.outcome is ProviderOutcome.PERMANENT_FAILURE:
                delivery.status = "FAILED"
                delivery.next_attempt_at = None
            elif delivery.attempt_count >= MAX_ATTEMPTS or delivery.expires_at <= now:
                delivery.status = "FAILED"
                delivery.next_attempt_at = None
            else:
                delivery.status = "RETRY_WAIT"
                delivery.next_attempt_at = now + timedelta(
                    seconds=self._retry_delay(delivery.attempt_count)
                )

    def recover_stuck(self) -> None:
        with self.database.transaction() as session:
            now = database_utc(session)
            for delivery in session.scalars(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.status == "IN_PROGRESS",
                    NotificationDelivery.lease_expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            ):
                attempt = session.scalar(
                    select(NotificationAttempt).where(
                        NotificationAttempt.delivery_id == delivery.id,
                        NotificationAttempt.attempt_no == delivery.attempt_count,
                    )
                )
                if attempt is not None and attempt.finished_at is None:
                    attempt.finished_at = now
                    attempt.outcome = ProviderOutcome.UNCERTAIN.value
                    attempt.error_category = "worker_crash"
                delivery.lease_token = None
                delivery.lease_expires_at = None
                delivery.last_error_category = "worker_crash"
                delivery.updated_at = now
                if delivery.superseded_at is not None:
                    delivery.status = "CANCELLED"
                    delivery.next_attempt_at = None
                elif delivery.expires_at <= now or delivery.attempt_count >= MAX_ATTEMPTS:
                    delivery.status = "FAILED"
                    delivery.next_attempt_at = None
                else:
                    delivery.status = "RETRY_WAIT"
                    delivery.next_attempt_at = now

    @staticmethod
    def _expire_unclaimed(session: Session, now: datetime) -> None:
        for delivery in session.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status.in_(("PENDING", "RETRY_WAIT")),
                NotificationDelivery.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        ):
            delivery.status = "FAILED"
            delivery.next_attempt_at = None
            delivery.last_error_category = "delivery_expired"
            delivery.updated_at = now

    def _retry_delay(self, attempt_no: int) -> float:
        base = float(min(RETRY_BASE_SECONDS * (2 ** (attempt_no - 1)), RETRY_MAX_SECONDS))
        return min(RETRY_MAX_SECONDS, max(0.0, base + self.jitter(base)))
