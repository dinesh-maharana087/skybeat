from app.notifications.sms import DisabledSMSProvider, FakeSMSProvider
from app.notifications.types import DeliveryMessage, ProviderOutcome


def message() -> DeliveryMessage:
    from datetime import UTC, datetime

    return DeliveryMessage(
        delivery_uuid="11111111-1111-1111-1111-111111111111",
        destination="+15551234567",
        event_kind="GPU_DEGRADED",
        project_name="Project",
        device_name="Device",
        incident_uuid="22222222-2222-2222-2222-222222222222",
        occurred_at=datetime(2026, 9, 23, tzinfo=UTC),
        opened_at=datetime(2026, 9, 23, tzinfo=UTC),
        closed_at=None,
    )


def test_fake_sms_provider_is_deterministic_and_never_uses_network():
    provider = FakeSMSProvider([ProviderOutcome.ACCEPTED, ProviderOutcome.TRANSIENT_FAILURE])

    accepted = provider.send(message())
    transient = provider.send(message())

    assert accepted.provider_message_id == "fake-sms-11111111-1111-1111-1111-111111111111"
    assert transient.outcome is ProviderOutcome.TRANSIENT_FAILURE
    assert provider.sent == [message(), message()]


def test_fake_sms_provider_exposes_all_durable_delivery_outcomes():
    provider = FakeSMSProvider([ProviderOutcome.PERMANENT_FAILURE, ProviderOutcome.UNCERTAIN])

    assert provider.send(message()).outcome is ProviderOutcome.PERMANENT_FAILURE
    assert provider.send(message()).outcome is ProviderOutcome.UNCERTAIN


def test_disabled_sms_provider_fails_closed_without_external_delivery():
    result = DisabledSMSProvider().send(message())

    assert result.outcome is ProviderOutcome.PERMANENT_FAILURE
    assert result.error_category == "sms_not_configured"
