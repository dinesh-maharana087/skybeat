from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.dashboard.management import EnrollmentResult
from app.dashboard.read import DashboardReadService
from app.dashboard.service import DashboardUser, LoginRedirect
from app.devices.credentials import GeneratedCredential
from app.devices.service import Conflict, NotFound
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


def test_development_dashboard_bypass_authenticates_dashboard_api_without_a_browser_session():
    class SessionMustNotRun:
        def authenticate_session(self, token):
            raise AssertionError(f"unexpected dashboard session lookup for {token!r}")

    class DashboardRead:
        def list_projects(self):
            return {
                "items": [{"project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd", "name": "Ops"}],
                "server_time": "2026-09-24T10:00:00.000000Z",
            }

    settings = Settings(
        env="development",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_development",
        dev_auth_bypass=True,
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = SessionMustNotRun()
    app.state.dashboard_read_service = DashboardRead()
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get("/api/v1/projects")

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd", "name": "Ops"}
    ]
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
            return {
                "counts": {"total": 1},
                "projects": [],
                "attention": [
                    {
                        "device_id": "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
                        "name": "edge-gpu-04",
                        "project": {
                            "project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd",
                            "name": "Ops",
                        },
                        "state": "OFFLINE",
                        "gpu_health": {"effective": "DRIVER_ERROR"},
                        "last_seen_at": "2026-09-23T10:00:00Z",
                        "has_active_incident": True,
                    }
                ],
                "server_time": "2026-09-23T10:00:00Z",
            }

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
    assert overview.json()["attention"][0]["state"] == "OFFLINE"
    assert overview.json()["attention"][0]["has_active_incident"] is True
    assert devices.status_code == 200
    assert devices.headers["cache-control"] == "no-store"


def test_authorized_incidents_and_history_use_bounded_read_projections():
    class AuthorizedSession:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    class DashboardRead:
        def list_incidents(self, *, limit, cursor, device_id):
            assert (limit, cursor, device_id) == (
                1,
                "incident-page-token",
                "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
            )
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
        incidents = client.get(
            "/api/v1/incidents?limit=1&cursor=incident-page-token&"
            "device_id=65f5cbda-529a-4f75-8ef1-aef3c57a5ff0"
        )
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


def test_invalid_incident_device_filter_is_rejected_before_database_access():
    class AuthorizedSession:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession()
    app.state.dashboard_read_service = DashboardReadService(object())
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/api/v1/incidents?device_id=not-a-canonical-uuid")

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


def test_dashboard_management_routes_require_the_existing_dashboard_user_and_no_store():
    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.post("/api/v1/projects", json={"name": "GPU Lab"})

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_cross_origin_dashboard_enrollment_is_rejected_before_management_service_execution():
    calls: list[object] = []

    class AuthorizedSession:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    def management_factory(database, actor):
        calls.append((database, actor))
        raise AssertionError("management service must not be created")

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession()
    app.state.dashboard_management_service_factory = management_factory
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.post(
            "/api/v1/devices",
            headers={"Origin": "https://other.example"},
            json={
                "name": "GPU node",
                "project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd",
                "gpu_monitoring_enabled": True,
                "expected_gpu_min_count": 1,
            },
        )

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert calls == []


def test_authorized_management_routes_forward_dashboard_actor_and_safe_projections_only():
    factory_actors: list[str] = []
    calls: list[tuple[str, object]] = []
    credential = GeneratedCredential(
        credential_id="e3e70682-c209-4cac-a29f-6fbed82c07cd",
        token=SecretStr("sb1.e3e70682-c209-4cac-a29f-6fbed82c07cd.test-secret"),
        digest=b"x" * 32,
    )

    class AuthorizedSession:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "ops@example.test", None)

    class Management:
        def create_project(self, request):
            calls.append(("project", request))
            return {"project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd", "name": request.name}

        def enroll_device(self, request):
            calls.append(("enroll", request))
            return EnrollmentResult(
                device={
                    "device_id": "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
                    "name": request.name,
                    "project_id": request.project_id,
                    "monitoring_enabled": True,
                    "gpu_monitoring_enabled": request.gpu_monitoring_enabled,
                    "expected_gpu_min_count": request.expected_gpu_min_count,
                },
                credential=credential,
            )

        def move_device(self, device_uuid, request):
            calls.append(("move", (device_uuid, request)))
            return {"device_id": device_uuid, "project_id": request.project_id}

        def set_device_enabled(self, device_uuid, request):
            calls.append(("enabled", (device_uuid, request)))
            return {"device_id": device_uuid, "monitoring_enabled": request.enabled}

    class DashboardRead:
        def list_projects(self):
            return {"items": [], "server_time": "2026-09-24T10:00:00Z"}

    def management_factory(database, actor):
        factory_actors.append(actor)
        return Management()

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession()
    app.state.dashboard_management_service_factory = management_factory
    app.state.dashboard_read_service = DashboardRead()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        project = client.post("/api/v1/projects", json={"name": "GPU Lab"})
        enrollment = client.post(
            "/api/v1/devices",
            json={
                "name": "GPU node",
                "project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd",
                "gpu_monitoring_enabled": True,
                "expected_gpu_min_count": 1,
            },
        )
        moved = client.patch(
            "/api/v1/devices/65f5cbda-529a-4f75-8ef1-aef3c57a5ff0/project",
            json={"project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd"},
        )
        enabled = client.patch(
            "/api/v1/devices/65f5cbda-529a-4f75-8ef1-aef3c57a5ff0/monitoring",
            json={"enabled": False},
        )
        later_read = client.get("/api/v1/projects")

    assert [response.status_code for response in (project, enrollment, moved, enabled)] == [200] * 4
    assert all(
        response.headers["cache-control"] == "no-store" for response in (project, enrollment)
    )
    assert project.json() == {
        "project": {"project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd", "name": "GPU Lab"}
    }
    assert enrollment.json()["credential"].startswith("sb1.")
    assert enrollment.json()["device"]["device_id"] == "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0"
    assert moved.json()["device"]["project_id"] == "e3e70682-c209-4cac-a29f-6fbed82c07cd"
    assert enabled.json()["device"]["monitoring_enabled"] is False
    assert "credential" not in later_read.text
    assert factory_actors == ["ops@example.test"] * 4
    assert [name for name, _ in calls] == ["project", "enroll", "move", "enabled"]


def test_dashboard_management_invalid_payloads_and_identity_errors_are_safe_no_store_4xx():
    class AuthorizedSession:
        def authenticate_session(self, token):
            return DashboardUser("google-user", "ops@example.test", None)

    class Management:
        def create_project(self, request):
            raise Conflict("project exists")

        def enroll_device(self, request):
            raise NotFound("project missing")

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession()
    app.state.dashboard_management_service_factory = lambda database, actor: Management()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        invalid = client.post("/api/v1/projects", json={"name": " "})
        conflict = client.post("/api/v1/projects", json={"name": "GPU Lab"})
        missing = client.post(
            "/api/v1/devices",
            json={
                "name": "GPU node",
                "project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd",
                "gpu_monitoring_enabled": True,
                "expected_gpu_min_count": 1,
            },
        )

    assert [response.status_code for response in (invalid, conflict, missing)] == [422, 409, 404]
    assert all(
        response.headers["cache-control"] == "no-store" for response in (invalid, conflict, missing)
    )
    assert "project exists" not in conflict.text
    assert "project missing" not in missing.text


def test_development_bypass_uses_the_same_dashboard_management_identity_boundary():
    actors: list[str] = []

    class Management:
        def create_project(self, request):
            return {"project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd", "name": request.name}

    def management_factory(database, actor):
        actors.append(actor)
        return Management()

    settings = Settings(
        env="development",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_development",
        public_base_url="https://testserver",
        dev_auth_bypass=True,
    )
    app = create_app(settings)
    app.state.dashboard_management_service_factory = management_factory
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/api/v1/projects", json={"name": "GPU Lab"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert actors == ["local-development@skybeat.invalid"]
