from fastapi.testclient import TestClient

from app.config import Settings
from app.dashboard.service import DashboardUser, LoginRedirect
from app.main import create_app


def test_dashboard_api_rejects_missing_browser_session_without_database_access():
    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/projects")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_authorized_dashboard_api_uses_read_projection_and_does_not_expose_delivery_destinations():
    class AuthorizedSession:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    class DashboardRead:
        def list_projects(self):
            return {
                "items": [{"project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd", "name": "Ops"}],
                "server_time": "2026-09-23T10:00:00.000000Z",
            }

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession()
    app.state.dashboard_read_service = DashboardRead()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/api/v1/projects")

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "Ops"
    assert response.headers["cache-control"] == "no-store"


def test_authorized_overview_and_device_filter_use_bounded_read_projection():
    class AuthorizedSession:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    class DashboardRead:
        def overview(self):
            return {"counts": {"total": 1}, "projects": [], "server_time": "2026-09-23T10:00:00Z"}

        def list_devices(self, **query):
            assert query == {
                "project_id": None,
                "state": None,
                "gpu_state": "DRIVER_ERROR",
                "include_disabled": False,
                "search": None,
                "cursor": "opaque-page-token",
                "limit": 1,
            }
            return {"items": [], "next_cursor": None, "server_time": "2026-09-23T10:00:00Z"}

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession()
    app.state.dashboard_read_service = DashboardRead()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        overview = client.get("/api/v1/dashboard/overview")
        devices = client.get(
            "/api/v1/devices?limit=1&gpu_state=DRIVER_ERROR&cursor=opaque-page-token"
        )

    assert overview.status_code == 200
    assert overview.headers["cache-control"] == "no-store"
    assert overview.json()["counts"] == {"total": 1}
    assert devices.status_code == 200
    assert devices.headers["cache-control"] == "no-store"


def test_authorized_incidents_and_history_use_bounded_read_projections():
    class AuthorizedSession:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    class DashboardRead:
        def list_incidents(self, *, limit, cursor):
            assert (limit, cursor) == (1, "incident-page-token")
            return {"items": [], "next_cursor": None, "server_time": "2026-09-23T10:00:00Z"}

        def device_history(self, device_uuid, range_name):
            assert (device_uuid, range_name) == (
                "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
                "6h",
            )
            return {"range": "6h", "truncated": False, "cpu_utilization": []}

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession()
    app.state.dashboard_read_service = DashboardRead()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        incidents = client.get("/api/v1/incidents?limit=1&cursor=incident-page-token")
        history = client.get(
            "/api/v1/devices/65f5cbda-529a-4f75-8ef1-aef3c57a5ff0/history?range=6h"
        )

    assert incidents.status_code == 200
    assert incidents.headers["cache-control"] == "no-store"
    assert history.status_code == 200
    assert history.headers["cache-control"] == "no-store"


def test_invalid_dashboard_read_query_keeps_no_store_response_header():
    class AuthorizedSession:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/api/v1/devices?gpu_state=not-a-state")

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_google_login_callback_and_logout_use_host_only_opaque_cookies():
    class FakeAuth:
        async def begin_login(self, redirect_uri):
            assert redirect_uri == "https://testserver/auth/google/callback"
            return LoginRedirect(
                "https://accounts.example.test/authorize", "browser-binding", "state"
            )

        async def complete_login(self, *, state, code, browser_binding, redirect_uri):
            assert (state, code, browser_binding) == ("state", "code", "browser-binding")
            assert redirect_uri == "https://testserver/auth/google/callback"
            return "new-opaque-session"

        def logout(self, token):
            assert token == "new-opaque-session"

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = FakeAuth()
    with TestClient(app, base_url="https://testserver") as client:
        login = client.get("/auth/google/login", follow_redirects=False)
        assert login.status_code == 307
        assert login.headers["location"] == "https://accounts.example.test/authorize"
        assert "__Host-skybeat_oauth=" in login.headers["set-cookie"]
        callback = client.get("/auth/google/callback?state=state&code=code", follow_redirects=False)
        assert callback.status_code == 303
        assert callback.headers["location"] == "/"
        assert "__Host-skybeat_session=" in callback.headers["set-cookie"]
        logout = client.post("/auth/logout")

    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]


def test_google_login_is_rate_limited_before_creating_oauth_transactions():
    class FakeAuth:
        async def begin_login(self, redirect_uri):
            return LoginRedirect("https://accounts.example.test/authorize", "binding", "state")

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = FakeAuth()
    with TestClient(app, base_url="https://testserver") as client:
        responses = [client.get("/auth/google/login", follow_redirects=False) for _ in range(7)]

    assert [response.status_code for response in responses[:6]] == [307] * 6
    assert responses[6].status_code == 429
    assert responses[6].headers["retry-after"] == "60"
