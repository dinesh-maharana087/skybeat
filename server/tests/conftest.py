"""MySQL tests only run against an explicitly selected, local test database."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from app.config import Settings
from app.db import Database

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_mysql_test_database_url(*, root: Path = REPOSITORY_ROOT) -> str | None:
    """Load only the dedicated test URL, with process configuration taking precedence."""
    raw = os.environ.get("SKYBEAT_TEST_DATABASE_URL")
    if raw is None:
        raw = dotenv_values(root / ".env", interpolate=False).get("SKYBEAT_TEST_DATABASE_URL")
    return raw


def require_isolated_mysql_test_url(raw: str) -> Settings:
    url = make_url(raw)
    if (
        url.drivername != "mysql+pymysql"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.database != "skybeat_test"
    ):
        pytest.fail("Refusing a database that is not the dedicated local skybeat_test database")
    return Settings(env="test", database_url=SecretStr(raw))


@pytest.fixture(scope="session")
def mysql_settings():
    raw = load_mysql_test_database_url()
    if not raw:
        pytest.skip("Set SKYBEAT_TEST_DATABASE_URL to an isolated local MySQL 8.x test database")
    return require_isolated_mysql_test_url(raw)


@pytest.fixture(scope="session")
def mysql_database(mysql_settings):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = mysql_settings
    command.upgrade(config, "head")
    database = Database(mysql_settings)
    yield database
    database.dispose()


@pytest.fixture
def identity(mysql_database):
    from app.devices.service import IdentityService

    return IdentityService(mysql_database, actor="pytest")
