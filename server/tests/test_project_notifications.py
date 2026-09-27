"""Stage 11 project notification policy primitives."""

from app.models import ProjectNotificationRecipient, ProjectNotificationSettings
from app.notifications.configuration import EventNotificationSettings, resolve_email_recipients


def test_unconfigured_project_uses_legacy_recipients_for_offline_event():
    assert resolve_email_recipients(
        settings=None,
        recipients=(),
        event_kind="DEVICE_OFFLINE",
        legacy_recipients=("ops@example.test",),
    ) == ("ops@example.test",)


def test_explicitly_configured_project_never_falls_back_and_honors_event_toggle():
    settings = EventNotificationSettings(
        device_offline_enabled=False,
        device_recovered_enabled=True,
        gpu_degraded_enabled=True,
        gpu_recovered_enabled=True,
    )
    assert (
        resolve_email_recipients(
            settings=settings,
            recipients=("Ops@Example.Test", "ops@example.test"),
            event_kind="DEVICE_OFFLINE",
            legacy_recipients=("legacy@example.test",),
        )
        == ()
    )
    assert resolve_email_recipients(
        settings=settings,
        recipients=("Ops@Example.Test", "ops@example.test"),
        event_kind="DEVICE_RECOVERED",
        legacy_recipients=("legacy@example.test",),
    ) == ("ops@example.test",)


def test_project_notification_models_enforce_one_settings_row_and_unique_normalized_recipient():
    assert ProjectNotificationSettings.__tablename__ == "project_notification_settings"
    assert ProjectNotificationRecipient.__tablename__ == "project_notification_recipients"
    unique_names = {
        constraint.name for constraint in ProjectNotificationRecipient.__table__.constraints
    }
    assert "project_email" in unique_names
