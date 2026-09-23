from fastapi.testclient import TestClient

from app.config import Settings
from app.dashboard.service import DashboardUser
from app.main import create_app


def test_dashboard_page_redirects_unauthenticated_browser_to_google_login():
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/google/login"


def test_dashboard_template_escapes_authenticated_identity_text():
    class Authenticated:
        def authenticate_session(self, token):
            assert token == "valid-browser-session"
            return DashboardUser("google-user", "<script>alert(1)</script>", None)

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Authenticated()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.get("/")

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert response.headers["cache-control"] == "no-store"
