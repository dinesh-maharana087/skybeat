"""Destructive MySQL tests are confined to the dedicated disposable database."""

import pytest
from conftest import load_mysql_test_database_url, require_isolated_mysql_test_url


def test_accepts_only_the_dedicated_local_skybeat_test_database():
    settings = require_isolated_mysql_test_url(
        "mysql+pymysql://test:synthetic@127.0.0.1/skybeat_test"
    )

    assert settings.database_url.get_secret_value().endswith("/skybeat_test")


@pytest.mark.parametrize(
    "url",
    [
        "mysql+pymysql://test:synthetic@127.0.0.1/skybeat",
        "mysql+pymysql://test:synthetic@127.0.0.1/other_test",
        "mysql+pymysql://test:synthetic@db.example.test/skybeat_test",
    ],
)
def test_rejects_runtime_or_non_dedicated_mysql_database(url):
    with pytest.raises(pytest.fail.Exception, match="skybeat_test"):
        require_isolated_mysql_test_url(url)


def test_loads_dedicated_test_url_from_root_env_with_process_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "SKYBEAT_TEST_DATABASE_URL=mysql+pymysql://test:from-env@127.0.0.1/skybeat_test\n",
        encoding="utf-8",
    )

    assert load_mysql_test_database_url(root=tmp_path) == (
        "mysql+pymysql://test:from-env@127.0.0.1/skybeat_test"
    )

    monkeypatch.setenv(
        "SKYBEAT_TEST_DATABASE_URL", "mysql+pymysql://test:from-process@127.0.0.1/skybeat_test"
    )

    assert load_mysql_test_database_url(root=tmp_path) == (
        "mysql+pymysql://test:from-process@127.0.0.1/skybeat_test"
    )
