import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_load_prefixed_environment(monkeypatch):
    monkeypatch.setenv(
        "SKYBEAT_DATABASE_URL", "mysql+pymysql://test:example@127.0.0.1/skybeat_test"
    )
    monkeypatch.setenv("SKYBEAT_ENV", "test")
    config = Settings()
    assert config.env == "test"
    assert config.db_pool_size == 5
    assert config.db_lock_timeout_seconds == 1
    assert config.allowed_hosts == ["localhost", "127.0.0.1", "testserver"]
    assert "example" not in repr(config)


def test_global_alert_email_recipients_are_normalized_and_validate_header_safety():
    config = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test",
        alert_email_recipients=["OPS@example.test"],
    )
    assert config.alert_email_recipients == ("ops@example.test",)
    with pytest.raises(ValidationError):
        Settings(
            env="test",
            database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test",
            alert_email_recipients=["ops@example.test\nBcc: attacker@example.test"],
        )


def test_empty_optional_smtp_environment_values_do_not_block_monitoring_without_recipients():
    config = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test",
        smtp_host="",
        smtp_from_address="",
        smtp_username="",
    )

    assert config.smtp_host is None
    assert config.smtp_from_address is None
    assert config.smtp_username is None


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///db.sqlite",
        "postgresql://user:pass@localhost/db",
        "mysql://user:pass@host/db",
        "mysql+pymysql://user@host/db",
        "mysql+pymysql://user:pass@host/",
        "mysql+pymysql://root:pass@host/db",
        "not-a-database-url",
    ],
)
def test_database_url_must_be_explicit_safe_mysql(url):
    with pytest.raises(ValidationError):
        Settings(env="test", database_url=url)


def test_production_requires_https_and_explicit_host_allowlist():
    base = dict(env="production", database_url="mysql+pymysql://runtime:example@mysql/skybeat")
    with pytest.raises(ValidationError):
        Settings(
            **base,
            public_base_url="http://monitor.example.com",
            allowed_hosts=["monitor.example.com"],
        )
    with pytest.raises(ValidationError):
        Settings(**base, public_base_url="https://monitor.example.com", allowed_hosts=["*"])
    config = Settings(
        **base, public_base_url="https://monitor.example.com", allowed_hosts=["monitor.example.com"]
    )
    assert not config.enable_api_docs


def test_url_and_errors_do_not_reveal_database_secret():
    config = Settings(env="test", database_url="mysql+pymysql://test:do-not-print@127.0.0.1/db")
    assert "do-not-print" not in str(config)
    with pytest.raises(ValidationError) as error:
        Settings(env="test", database_url="mysql+pymysql://root:do-not-print@127.0.0.1/db")
    assert "do-not-print" not in str(error.value)


def test_invalid_port_does_not_echo_configuration_fragment():
    with pytest.raises(ValidationError) as error:
        Settings(env="test", database_url="mysql+pymysql://user:example@localhost:private-value/db")
    assert "private-value" not in str(error.value)


@pytest.mark.parametrize(
    "setting,value",
    [
        ("db_pool_size", 0),
        ("db_pool_timeout_seconds", 0),
        ("db_read_timeout_seconds", 0),
        ("db_lock_timeout_seconds", 0),
        ("db_connect_timeout_seconds", 0),
    ],
)
def test_external_operation_limits_are_positive(setting, value):
    with pytest.raises(ValidationError):
        Settings(
            env="test", database_url="mysql+pymysql://test:example@localhost/db", **{setting: value}
        )
