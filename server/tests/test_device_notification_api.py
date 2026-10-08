"""Stage 12D device routing endpoints retain dashboard role and origin checks."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dashboard.service import DashboardUser
from app.main import create_app
from app.notifications.management import NotificationRecipientUnavailable
from app.users.service import UserRole

PROJECT_ID = "e3e70682-c209-4cac-a29f-6fbed82c07cd"
DEVICE_ID = "123e4567-e89b-42d3-a456-426614174000"
POLICY = {
    "recipients": ["Charlie@Example.Test"],
    "device_offline_enabled": True,
    "device_recovered_enabled": True,
    "gpu_degraded_enabled": False,
    "gpu_recovered_enabled": True,
}


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.ADMIN])
def test_device_routing_api_lists_saves_and_resets_for_managers(role):
    calls: list[tuple[object, ...]] = []

    class Session:
        def authenticate_session(self, token):
            return DashboardUser("sub", "ops@example.test", None, 1, role)

    class Notifications:
        def list_devices(self, project_id, *, legacy_recipients):
            calls.append(("list", project_id, legacy_recipients))
            return {"items": [{"device_id": DEVICE_ID, "mode": "INHERIT_PROJECT"}]}

        def update_device(self, project_id, device_id, payload):
            calls.append(("save", project_id, device_id, payload))
            return {"device_id": device_id, "mode": "CUSTOM"}

        def reset_device(self, project_id, device_id):
            calls.append(("reset", project_id, device_id))
            return {"device_id": device_id, "mode": "INHERIT_PROJECT"}

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
        alert_email_recipients=("legacy@example.test",),
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()
    app.state.notification_management_service_factory = lambda database, *, actor: Notifications()
    path = f"/api/v1/notifications/{PROJECT_ID}/devices"
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        listed = client.get(path)
        saved = client.put(f"{path}/{DEVICE_ID}", json=POLICY)
        reset = client.delete(f"{path}/{DEVICE_ID}")

    assert (listed.status_code, saved.status_code, reset.status_code) == (200, 200, 200)
    assert listed.json()["items"][0]["mode"] == "INHERIT_PROJECT"
    assert saved.json()["notification"]["mode"] == "CUSTOM"
    assert reset.json()["notification"]["mode"] == "INHERIT_PROJECT"
    assert calls[0] == ("list", PROJECT_ID, ("legacy@example.test",))
    assert calls[1][1:3] == (PROJECT_ID, DEVICE_ID)
    assert calls[1][3].recipients == ["charlie@example.test"]
    assert calls[2] == ("reset", PROJECT_ID, DEVICE_ID)
    assert all(
        response.headers["cache-control"] == "no-store" for response in (listed, saved, reset)
    )


def test_device_routing_api_rejects_user_and_duplicate_recipients():
    class Session:
        def authenticate_session(self, token):
            return DashboardUser("sub", "user@example.test", None, 1, UserRole.USER)

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()
    app.state.notification_management_service_factory = lambda *args, **kwargs: (
        _ for _ in ()
    ).throw(AssertionError("USER must not reach notification management"))
    path = f"/api/v1/notifications/{PROJECT_ID}/devices/{DEVICE_ID}"
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        forbidden = client.put(path, json=POLICY)
        forbidden_reset = client.delete(path)
        forbidden_list = client.get(f"/api/v1/notifications/{PROJECT_ID}/devices")

    assert forbidden.status_code == forbidden_reset.status_code == forbidden_list.status_code == 403


def test_device_routing_api_validates_duplicate_recipients_and_origin():
    class Session:
        def authenticate_session(self, token):
            return DashboardUser("sub", "admin@example.test", None, 1, UserRole.ADMIN)

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()

    class Notifications:
        def update_device(self, *args):
            raise AssertionError("invalid request must not reach service")

        def reset_device(self, *args):
            raise AssertionError("invalid request must not reach service")

    app.state.notification_management_service_factory = lambda *args, **kwargs: Notifications()
    path = f"/api/v1/notifications/{PROJECT_ID}/devices/{DEVICE_ID}"
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        duplicate = client.put(
            path, json={**POLICY, "recipients": ["Charlie@Example.Test", "charlie@example.test"]}
        )
        invalid_device = client.delete(f"/api/v1/notifications/{PROJECT_ID}/devices/not-a-uuid")
        cross_origin = client.put(
            path, json=POLICY, headers={"Origin": "https://foreign.example.test"}
        )

    assert duplicate.status_code == invalid_device.status_code == 422
    assert cross_origin.status_code == 403


def test_device_routing_api_reports_unavailable_recipient_as_invalid_input():
    class Session:
        def authenticate_session(self, token):
            return DashboardUser("sub", "admin@example.test", None, 1, UserRole.ADMIN)

    class Notifications:
        def update_device(self, project_id, device_id, payload):
            raise NotificationRecipientUnavailable()

    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = Session()
    app.state.notification_management_service_factory = lambda database, *, actor: Notifications()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", "valid-browser-session")
        response = client.put(
            f"/api/v1/notifications/{PROJECT_ID}/devices/{DEVICE_ID}", json=POLICY
        )

    assert response.status_code == 422
