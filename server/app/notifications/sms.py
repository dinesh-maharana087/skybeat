"""Provider-neutral SMS test adapter; no production network adapter is configured in V1."""

from collections import deque
from collections.abc import Iterable

from app.notifications.types import DeliveryMessage, ProviderOutcome, ProviderResult


class FakeSMSProvider:
    """Deterministic in-memory provider for tests and explicit non-production use."""

    def __init__(self, outcomes: Iterable[ProviderOutcome] = ()) -> None:
        self._outcomes = deque(outcomes)
        self.sent: list[DeliveryMessage] = []

    def send(self, message: DeliveryMessage) -> ProviderResult:
        self.sent.append(message)
        outcome = self._outcomes.popleft() if self._outcomes else ProviderOutcome.ACCEPTED
        message_id = None
        if outcome is ProviderOutcome.ACCEPTED:
            message_id = f"fake-sms-{message.delivery_uuid}"
        category = None if outcome is ProviderOutcome.ACCEPTED else "fake_sms_failure"
        return ProviderResult(outcome, category, message_id)


class DisabledSMSProvider:
    """Safe no-op used until a separately approved real SMS adapter is configured."""

    def send(self, message: DeliveryMessage) -> ProviderResult:
        del message
        return ProviderResult(ProviderOutcome.PERMANENT_FAILURE, "sms_not_configured")
