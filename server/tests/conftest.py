"""MySQL tests only run against an explicitly selected, local test database."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.config import Settings
from app.db import Database


@pytest.fixture(scope="session")
def mysql_settings():
    raw = os.environ.get("SKYBEAT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set SKYBEAT_TEST_DATABASE_URL to an isolated local MySQL 8.x test database")
    url = make_url(raw)
    if (
        url.drivername != "mysql+pymysql"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not url.database
        or not url.database.endswith("_test")
    ):
        pytest.fail("Refusing a database that is not explicitly local and suffixed _test")
    return Settings(env="test", database_url=raw)


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
