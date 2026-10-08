from unittest.mock import Mock

import pytest

from app.local_schema_guard import SchemaMismatch, require_current_schema


def test_current_schema_is_accepted():
    require_current_schema({"c1436a7392a9"}, {"c1436a7392a9"})


def test_behind_schema_has_actionable_error():
    with pytest.raises(SchemaMismatch) as error:
        require_current_schema({"2f4a6c8d10b2"}, {"c1436a7392a9"})
    assert "Database: 2f4a6c8d10b2" in str(error.value)
    assert "Required: c1436a7392a9" in str(error.value)
    assert "alembic upgrade head" in str(error.value)


def test_missing_schema_and_multiple_code_heads_fail_closed():
    with pytest.raises(SchemaMismatch):
        require_current_schema(set(), {"c1436a7392a9"})
    with pytest.raises(SchemaMismatch, match="exactly one Alembic head"):
        require_current_schema({"c1436a7392a9"}, {"a", "b"})


def test_production_startup_does_not_run_schema_guard(monkeypatch):
    from app.config import Settings
    from app.main import create_app

    guard = Mock(side_effect=AssertionError("local-only guard must not run"))
    monkeypatch.setattr("app.local_schema_guard.run", guard)
    create_app(Settings(env="test", database_url="mysql+pymysql://test:example@127.0.0.1/db"))
    guard.assert_not_called()
