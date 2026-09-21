from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.main import create_app


def config():
    return Settings(env="test", database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test")


def test_liveness_does_not_need_database_and_shutdown_disposes_pool():
    database = Database(config())
    database.ready = Mock(return_value=False)
    database.dispose = Mock()
    with TestClient(create_app(config(), database=database)) as client:
        assert client.get("/livez").json() == {"status": "ok"}
        database.ready.assert_not_called()
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert response.headers["cache-control"] == "no-store"
    database.dispose.assert_called_once()


def test_ready_response_is_minimal_when_checks_pass():
    database = Database(config())
    database.ready = Mock(return_value=True)
    with TestClient(create_app(config(), database=database)) as client:
        assert client.get("/readyz").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.post("/api/v1/heartbeats").status_code == 404
        assert client.get("/livez", headers={"host": "attacker.invalid"}).status_code == 400


def test_unexpected_error_is_safe_and_has_server_generated_request_id():
    app = create_app(config())

    @app.get("/test-error")
    def test_error():
        raise RuntimeError("Authorization: Bearer should-never-leak")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error", headers={"x-request-id": "untrusted-id"})
        assert response.status_code == 500
        assert "should-never-leak" not in response.text
        assert response.json()["error"]["code"] == "internal_error"
        assert response.json()["error"]["request_id"] != "untrusted-id"
