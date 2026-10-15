"""Forward repair of the lifecycle failure-detail schema drift."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "d8a71f2c4e30_stage12jp3_lifecycle_failure_detail.py"
)


def load_migration() -> ModuleType:
    assert MIGRATION_PATH.is_file(), "Stage 12J-P.3A forward migration is missing."
    spec = importlib.util.spec_from_file_location(
        "stage12jp3_lifecycle_failure_detail", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeInspector:
    def __init__(self, *, table_exists: bool, columns: list[dict[str, object]]) -> None:
        self.table_exists = table_exists
        self.columns = columns

    def has_table(self, table_name: str) -> bool:
        assert table_name == "device_agent_lifecycle"
        return self.table_exists

    def get_columns(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "device_agent_lifecycle"
        return self.columns


def configure_migration(monkeypatch, migration, inspector: FakeInspector) -> list[object]:
    added: list[object] = []
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: False),
    )
    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.op, "add_column", lambda _table, column: added.append(column))
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    return added


def test_upgrade_adds_nullable_varchar_64_when_failure_detail_is_missing(monkeypatch):
    migration = load_migration()
    added = configure_migration(
        monkeypatch,
        migration,
        FakeInspector(table_exists=True, columns=[{"name": "device_id"}]),
    )

    migration.upgrade()

    assert len(added) == 1
    column = added[0]
    assert column.name == "failure_detail"
    assert column.type.length == 64
    assert column.nullable is True


def test_upgrade_rejects_missing_lifecycle_table(monkeypatch):
    migration = load_migration()
    configure_migration(monkeypatch, migration, FakeInspector(table_exists=False, columns=[]))

    with pytest.raises(RuntimeError, match="device_agent_lifecycle"):
        migration.upgrade()


def test_upgrade_rejects_incompatible_existing_failure_detail(monkeypatch):
    migration = load_migration()
    configure_migration(
        monkeypatch,
        migration,
        FakeInspector(
            table_exists=True,
            columns=[{"name": "failure_detail", "type": migration.sa.String(32), "nullable": True}],
        ),
    )

    with pytest.raises(RuntimeError, match=r"VARCHAR\(64\) NULL"):
        migration.upgrade()


def test_upgrade_leaves_compatible_existing_failure_detail_unchanged(monkeypatch):
    migration = load_migration()
    added = configure_migration(
        monkeypatch,
        migration,
        FakeInspector(
            table_exists=True,
            columns=[{"name": "failure_detail", "type": migration.sa.String(64), "nullable": True}],
        ),
    )

    migration.upgrade()

    assert added == []


def test_upgrade_rejects_offline_sql_generation(monkeypatch):
    migration = load_migration()
    configure_migration(
        monkeypatch,
        migration,
        FakeInspector(
            table_exists=True,
            columns=[{"name": "failure_detail", "type": migration.sa.String(64), "nullable": True}],
        ),
    )
    monkeypatch.setattr(
        migration,
        "context",
        SimpleNamespace(is_offline_mode=lambda: True),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="offline SQL"):
        migration.upgrade()


@pytest.mark.mysql
def test_mysql_forward_repair_preserves_rows_and_rejects_incompatible_schema(
    mysql_database, mysql_settings
):
    """Exercise the repair only through the local database guarded by mysql_settings."""
    from app.db import database_utc
    from app.devices.service import IdentityService
    from app.models import DeviceAgentLifecycle

    identity = IdentityService(mysql_database, actor="stage12jp3-schema-test")
    project = identity.create_project("Stage 12J-P.3A schema test")
    enrolled = identity.enroll(project.public_id, "Lifecycle schema test")
    with mysql_database.transaction() as session:
        now = database_utc(session)
        session.add(
            DeviceAgentLifecycle(
                device_id=enrolled.device.id,
                operation_uuid="00000000-0000-4000-8000-000000000001",
                action="UPGRADE",
                state="FAILED",
                target_version="1.0.5",
                target_wheel_sha256="a" * 64,
                archive_sha256="b" * 64,
                previous_version=None,
                previous_wheel_sha256=None,
                rollback_available=False,
                requester="stage12jp3-schema-test",
                failure_category="verification_failed",
                failure_detail="wheel_hash_mismatch",
                requested_at=now,
                updated_at=now,
                completed_at=now,
            )
        )

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["settings"] = mysql_settings
    try:
        with mysql_database.engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE device_agent_lifecycle DROP COLUMN failure_detail"
            )
            connection.execute(text("UPDATE alembic_version SET version_num = '93f20b4c17d6'"))

        command.upgrade(config, "head")

        columns = inspect(mysql_database.engine).get_columns("device_agent_lifecycle")
        repaired = next(column for column in columns if column["name"] == "failure_detail")
        assert repaired["type"].length == 64
        assert repaired["nullable"] is True
        with mysql_database.transaction() as session:
            repaired_row = session.get(DeviceAgentLifecycle, enrolled.device.id)
            assert repaired_row is not None
            assert repaired_row.operation_uuid == "00000000-0000-4000-8000-000000000001"
            assert repaired_row.failure_detail is None

        with mysql_database.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = '93f20b4c17d6'"))
        command.upgrade(config, "head")
        columns_after_noop = inspect(mysql_database.engine).get_columns("device_agent_lifecycle")
        assert sum(column["name"] == "failure_detail" for column in columns_after_noop) == 1

        with mysql_database.engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE device_agent_lifecycle MODIFY COLUMN failure_detail VARCHAR(32) NULL"
            )
            connection.execute(text("UPDATE alembic_version SET version_num = '93f20b4c17d6'"))
        with pytest.raises(RuntimeError, match=r"VARCHAR\(64\) NULL"):
            command.upgrade(config, "head")
    finally:
        with mysql_database.engine.begin() as connection:
            columns = inspect(connection).get_columns("device_agent_lifecycle")
            failure_detail = next(
                (column for column in columns if column["name"] == "failure_detail"), None
            )
            if failure_detail is None:
                connection.exec_driver_sql(
                    "ALTER TABLE device_agent_lifecycle ADD COLUMN failure_detail VARCHAR(64) NULL"
                )
            elif failure_detail["type"].length != 64 or failure_detail["nullable"] is not True:
                connection.exec_driver_sql(
                    "ALTER TABLE device_agent_lifecycle MODIFY COLUMN "
                    "failure_detail VARCHAR(64) NULL"
                )
            connection.execute(text("UPDATE alembic_version SET version_num = '93f20b4c17d6'"))
        command.upgrade(config, "head")
