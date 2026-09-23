from threading import Event

from app.config import Settings
from app.worker import build_notification_providers, build_smtp_provider, run_loop, run_once


def _settings(**values):
    return Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test",
        **values,
    )


def test_worker_builds_smtp_provider_only_from_protected_complete_configuration():
    assert build_smtp_provider(_settings()) is None

    provider = build_smtp_provider(
        _settings(
            smtp_host="smtp.example.test",
            smtp_from_address="skybeat@example.test",
            smtp_username="skybeat",
            smtp_password="secret-not-to-log",
        )
    )

    assert provider is not None
    assert provider.host == "smtp.example.test"


def test_worker_uses_a_safe_sms_noop_until_a_vendor_adapter_is_approved():
    providers = build_notification_providers(
        _settings(sms_enabled=True, alert_sms_recipients=("+15551234567",))
    )

    assert set(providers) == {"SMS"}
    assert providers["SMS"].send is not None


def test_worker_run_once_sweeps_before_claiming_notification_work(monkeypatch):
    calls = []

    class Health:
        def __init__(
            self,
            database,
            *,
            email_recipients,
            sms_recipients,
            suspect_after_seconds,
            offline_after_seconds,
        ):
            assert email_recipients == ()
            assert sms_recipients == ()
            assert (suspect_after_seconds, offline_after_seconds) == (75, 180)

        def sweep(self):
            calls.append("sweep")

    class Notifications:
        def __init__(self, database):
            pass

        def process_due(self, provider, *, limit):
            calls.append(("deliver", provider, limit))

    monkeypatch.setattr("app.worker.AvailabilityService", Health)
    monkeypatch.setattr("app.worker.NotificationService", Notifications)

    run_once(_settings(), object(), provider=object())

    assert calls == ["sweep", ("deliver", calls[1][1], 4)]


def test_worker_loop_uses_notification_poll_interval_and_stops_without_new_work(monkeypatch):
    calls = []
    stop = Event()
    now = [0.0]

    class Health:
        def __init__(self, *_args, **_kwargs):
            pass

        def sweep(self):
            calls.append("sweep")

    class Notifications:
        def __init__(self, *_args, **_kwargs):
            pass

        def process_due(self, provider, *, limit):
            calls.append(("deliver", provider, limit))

    def wait(seconds):
        now[0] += seconds
        if now[0] >= 4:
            stop.set()
        return stop.is_set()

    monkeypatch.setattr("app.worker.AvailabilityService", Health)
    monkeypatch.setattr("app.worker.NotificationService", Notifications)

    run_loop(
        _settings(health_sweep_seconds=5, notification_poll_seconds=2),
        object(),
        {"EMAIL": object()},
        stop,
        monotonic=lambda: now[0],
        wait=wait,
    )

    assert calls == ["sweep", ("deliver", calls[1][1], 4), ("deliver", calls[2][1], 4)]
