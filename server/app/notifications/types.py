"""Provider-neutral notification values."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ProviderOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class ProviderResult:
    outcome: ProviderOutcome
    error_category: str | None = None
    provider_message_id: str | None = None


@dataclass(frozen=True)
class DeliveryMessage:
    delivery_uuid: str
    destination: str
    event_kind: str
    project_name: str
    device_name: str
    incident_uuid: str
    occurred_at: datetime
    opened_at: datetime
    closed_at: datetime | None
