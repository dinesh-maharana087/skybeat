from app.config import Settings
from app.worker import build_smtp_provider, run_once


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


def test_worker_run_once_sweeps_before_claiming_notification_work(monkeypatch):
    calls = []

    class Health:
        def __init__(self, database, *, email_recipients):
            assert email_recipients == ()

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
