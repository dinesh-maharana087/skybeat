"""Alembic uses the dedicated migration account without changing runtime settings."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.config import DatabaseSettings
from app.migration_config import load_migration_database_settings

SERVER = Path(__file__).resolve().parents[1]
RUNTIME_URL = "mysql+pymysql://runtime:runtime-secret@127.0.0.1/runtime_test"
MIGRATION_URL = "mysql+pymysql://migration:migration-secret@127.0.0.1/migration_test"


def test_migration_url_is_discovered_from_canonical_root_independent_of_cwd(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        f"SKYBEAT_DATABASE_URL={RUNTIME_URL}\n"
        f"SKYBEAT_MIGRATION_DATABASE_URL={MIGRATION_URL}\n"
        "SKYBEAT_DB_CONNECT_TIMEOUT_SECONDS=4\n"
        "SKYBEAT_ALERT_SMS_RECIPIENTS=invalid\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SKYBEAT_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setenv("SKYBEAT_DATABASE_URL", RUNTIME_URL)
    monkeypatch.chdir(tmp_path.parent)

    settings = load_migration_database_settings(root=tmp_path)

    assert isinstance(settings, DatabaseSettings)
    assert settings.database_url.get_secret_value() == MIGRATION_URL
    assert settings.db_connect_timeout_seconds == 4


def test_process_migration_url_and_database_options_override_root_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        f"SKYBEAT_MIGRATION_DATABASE_URL={MIGRATION_URL}\nSKYBEAT_DB_CONNECT_TIMEOUT_SECONDS=4\n",
        encoding="utf-8",
    )
    override = "mysql+pymysql://override:process-secret@127.0.0.1/override_test"
    monkeypatch.setenv("SKYBEAT_MIGRATION_DATABASE_URL", override)
    monkeypatch.setenv("SKYBEAT_DB_CONNECT_TIMEOUT_SECONDS", "5")

    settings = load_migration_database_settings(root=tmp_path)

    assert settings.database_url.get_secret_value() == override
    assert settings.db_connect_timeout_seconds == 5


def test_runtime_url_cannot_substitute_for_missing_migration_url(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"SKYBEAT_DATABASE_URL={RUNTIME_URL}\n", encoding="utf-8")
    monkeypatch.delenv("SKYBEAT_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setenv("SKYBEAT_DATABASE_URL", RUNTIME_URL)

    with pytest.raises(RuntimeError, match="SKYBEAT_MIGRATION_DATABASE_URL") as failure:
        load_migration_database_settings(root=tmp_path)

    assert "runtime-secret" not in str(failure.value)


def test_invalid_migration_url_never_reveals_credential(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "SKYBEAT_MIGRATION_DATABASE_URL=mysql+pymysql://root:private-value@127.0.0.1/db\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SKYBEAT_MIGRATION_DATABASE_URL", raising=False)

    with pytest.raises(ValueError) as failure:
        load_migration_database_settings(root=tmp_path)

    assert "private-value" not in str(failure.value)


def test_alembic_cli_invalid_migration_url_redacts_credential():
    environment = os.environ.copy()
    environment["SKYBEAT_MIGRATION_DATABASE_URL"] = (
        "mysql+pymysql://root:private-value@127.0.0.1/unsafe"
    )
    result = subprocess.run(  # noqa: S603 - fixed Python executable and Alembic arguments
        [sys.executable, "-m", "alembic", "current"],
        cwd=SERVER,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert "private-value" not in result.stdout + result.stderr


@pytest.mark.mysql
def test_alembic_cli_current_uses_migration_url_from_server_and_repository_root(mysql_database):
    with mysql_database.engine.connect() as connection:
        expected = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
    test_url = mysql_database.engine.url.render_as_string(hide_password=False)
    environment = os.environ.copy()
    environment["SKYBEAT_MIGRATION_DATABASE_URL"] = test_url
    environment["SKYBEAT_DATABASE_URL"] = RUNTIME_URL
    for cwd, config_arguments in (
        (SERVER, []),
        (SERVER.parent, ["-c", str(SERVER / "alembic.ini")]),
    ):
        for action in ("current", "heads", "history"):
            result = subprocess.run(  # noqa: S603 - fixed Python executable and Alembic arguments
                [sys.executable, "-m", "alembic", *config_arguments, action],
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            assert result.returncode == 0
            assert expected in result.stdout
            if action == "current":
                assert "runtime_test" not in result.stdout
            assert "runtime-secret" not in result.stdout + result.stderr
            assert "migration-secret" not in result.stdout + result.stderr


@pytest.mark.mysql
def test_programmatic_alembic_settings_override_cli_discovery(
    mysql_database, mysql_settings, monkeypatch
):
    output = io.StringIO()
    config = Config(str(SERVER / "alembic.ini"), stdout=output)
    config.attributes["settings"] = mysql_settings
    monkeypatch.setenv("SKYBEAT_MIGRATION_DATABASE_URL", RUNTIME_URL)

    command.current(config)

    assert "d8a71f2c4e30" in output.getvalue()
