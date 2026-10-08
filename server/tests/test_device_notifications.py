"""Stage 12D routing precedence without a database or SMTP transport."""

from app.models import Base
from app.notifications import configuration
from app.notifications.configuration import EventNotificationSettings, resolve_email_recipients

ALL_EVENTS = EventNotificationSettings(True, True, True, True)
OFFLINE_DISABLED = EventNotificationSettings(False, True, True, True)


def _resolve(
    *,
    project_settings: EventNotificationSettings | None = ALL_EVENTS,
    project_recipients: tuple[str, ...] = ("alice@example.test", "bob@example.test"),
    device_settings: EventNotificationSettings | None = None,
    device_recipients: tuple[str, ...] = (),
    event_kind: str = "DEVICE_OFFLINE",
) -> tuple[str, ...]:
    return resolve_email_recipients(
        settings=project_settings,
        recipients=project_recipients,
        device_settings=device_settings,
        device_recipients=device_recipients,
        event_kind=event_kind,
        legacy_recipients=("legacy@example.test",),
    )


def test_device_without_override_inherits_project_and_unconfigured_fallback():
    assert _resolve() == ("alice@example.test", "bob@example.test")
    assert _resolve(project_settings=None) == ("legacy@example.test",)
    assert _resolve(project_settings=ALL_EVENTS, project_recipients=()) == ()


def test_device_override_replaces_project_and_never_merges_recipients():
    assert _resolve(device_settings=ALL_EVENTS, device_recipients=("charlie@example.test",)) == (
        "charlie@example.test",
    )
    assert _resolve(device_settings=ALL_EVENTS, device_recipients=()) == ()
    assert (
        _resolve(
            project_settings=None,
            device_settings=ALL_EVENTS,
            device_recipients=(),
        )
        == ()
    )


def test_device_disabled_event_suppresses_only_its_event():
    assert (
        _resolve(
            device_settings=OFFLINE_DISABLED,
            device_recipients=("charlie@example.test",),
        )
        == ()
    )
    assert _resolve(
        device_settings=OFFLINE_DISABLED,
        device_recipients=("charlie@example.test",),
        event_kind="DEVICE_RECOVERED",
    ) == ("charlie@example.test",)


def test_project_changes_affect_inherited_devices_but_not_custom_devices():
    before = _resolve()
    after = _resolve(project_recipients=("alice@example.test", "david@example.test"))
    custom_before = _resolve(
        device_settings=ALL_EVENTS, device_recipients=("charlie@example.test",)
    )
    custom_after = _resolve(
        project_recipients=("alice@example.test", "david@example.test"),
        device_settings=ALL_EVENTS,
        device_recipients=("charlie@example.test",),
    )
    assert before == ("alice@example.test", "bob@example.test")
    assert after == ("alice@example.test", "david@example.test")
    assert custom_before == custom_after == ("charlie@example.test",)


def test_device_routing_has_one_override_and_unique_recipient_per_device():
    settings = Base.metadata.tables["device_notification_settings"]
    recipients = Base.metadata.tables["device_notification_recipients"]
    assert [column.name for column in settings.primary_key.columns] == ["device_id"]
    assert any(
        {column.name for column in constraint.columns} == {"device_id", "email"}
        for constraint in recipients.constraints
        if hasattr(constraint, "columns")
    )
    assert all(foreign_key.ondelete == "CASCADE" for foreign_key in settings.foreign_keys)
    assert all(foreign_key.ondelete == "CASCADE" for foreign_key in recipients.foreign_keys)


def test_effective_policy_exposes_source_and_recipients_without_hiding_disabled_events():
    policy = configuration.select_email_policy(
        project_settings=ALL_EVENTS,
        project_recipients=("alice@example.test",),
        device_settings=OFFLINE_DISABLED,
        device_recipients=("charlie@example.test",),
        legacy_recipients=("legacy@example.test",),
    )
    assert policy.source == "DEVICE"
    assert policy.recipients == ("charlie@example.test",)
    assert policy.settings == OFFLINE_DISABLED
