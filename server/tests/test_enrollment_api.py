from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dashboard.service import DashboardUser
from app.main import create_app
from app.users.service import UserRole

TOKEN_SECRET = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ENROLLMENT_TOKEN = f"sbe1.e3e70682-c209-4cac-a29f-6fbed82c07cd.{TOKEN_SECRET}"
VERIFICATION_TOKEN = f"sbv1.e3e70682-c209-4cac-a29f-6fbed82c07cd.{TOKEN_SECRET}"


class AuthorizedSession:
    def __init__(self, role: UserRole) -> None:
        self.role = role

    def authenticate_session(self, token: str) -> DashboardUser:
        assert token == "browser-session"
        return DashboardUser(
            "google-user", "operator@example.test", None, user_id=1, role=self.role
        )


class FakeEnrollmentService:
    last_expected_replacement_device_uuid: str | None = None

    def __init__(self, database: object, *, actor: str) -> None:
        self.database = database
        self.actor = actor

    def create_intent(self, **request: object) -> SimpleNamespace:
        return SimpleNamespace(
            enrollment=SimpleNamespace(
                public_id="e3e70682-c209-4cac-a29f-6fbed82c07cd",
                expires_at=datetime(2026, 9, 25, 10, 10),
            ),
            token=SimpleNamespace(value=ENROLLMENT_TOKEN),
        )

    def exchange(
        self, token: object, *, expected_replacement_device_uuid: str | None = None
    ) -> SimpleNamespace:
        assert token == ENROLLMENT_TOKEN
        assert expected_replacement_device_uuid in {None, "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0"}
        type(self).last_expected_replacement_device_uuid = expected_replacement_device_uuid
        return SimpleNamespace(
            device=SimpleNamespace(device_uuid="65f5cbda-529a-4f75-8ef1-aef3c57a5ff0"),
            credential=SimpleNamespace(
                token=SimpleNamespace(
                    get_secret_value=lambda: "sb1.65f5cbda-529a-4f75-8ef1-aef3c57a5ff0.secret"
                )
            ),
            verification_token=SimpleNamespace(value=VERIFICATION_TOKEN),
        )

    def verify_receipt(self, token: object) -> SimpleNamespace:
        assert token == VERIFICATION_TOKEN
        return SimpleNamespace(accepted_heartbeat=False)


def client_for(role: UserRole) -> TestClient:
    settings = Settings(
        env="test",
        database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test",
        public_base_url="https://testserver",
    )
    app = create_app(settings)
    app.state.dashboard_auth_service = AuthorizedSession(role)
    app.state.agent_enrollment_service_factory = FakeEnrollmentService
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set("__Host-skybeat_session", "browser-session")
    return client


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.ADMIN])
def test_owner_and_admin_can_create_one_time_enrollment_intents(role: UserRole):
    with client_for(role) as client:
        response = client.post(
            "/api/v1/agent-enrollments",
            headers={"Origin": "https://testserver"},
            json={
                "mode": "NEW",
                "project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd",
                "name": "GPU node",
                "gpu_monitoring_enabled": True,
                "expected_gpu_min_count": 1,
            },
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "enrollment": {
            "enrollment_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd",
            "expires_at": "2026-09-25T10:10:00",
        },
        "token": ENROLLMENT_TOKEN,
    }


def test_user_and_unauthenticated_callers_cannot_create_enrollment_intents():
    with client_for(UserRole.USER) as client:
        user_response = client.post(
            "/api/v1/agent-enrollments",
            headers={"Origin": "https://testserver"},
            json={
                "mode": "NEW",
                "project_id": "e3e70682-c209-4cac-a29f-6fbed82c07cd",
                "name": "GPU node",
            },
        )
    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1:1/skybeat_test"
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        anonymous_response = client.post("/api/v1/agent-enrollments", json={})

    assert user_response.status_code == 403
    assert anonymous_response.status_code == 401


def test_exchange_and_receipt_routes_are_anonymous_but_strictly_scoped():
    with client_for(UserRole.OWNER) as client:
        exchanged = client.post(
            "/api/v1/agent-enrollments/exchange",
            headers={"Authorization": f"Bearer {ENROLLMENT_TOKEN}"},
        )
        verified = client.get(
            "/api/v1/agent-enrollments/verification",
            headers={"Authorization": f"Bearer {VERIFICATION_TOKEN}"},
        )

    assert exchanged.status_code == 200
    assert exchanged.json()["device_id"] == "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0"
    assert exchanged.json()["credential"].startswith("sb1.")
    assert exchanged.json()["verification_token"].startswith("sbv1.")
    assert verified.status_code == 200
    assert verified.json() == {"accepted_heartbeat": False}


def test_exchange_and_receipt_routes_reject_missing_or_wrong_bearer_tokens():
    with client_for(UserRole.OWNER) as client:
        missing = client.post("/api/v1/agent-enrollments/exchange")
        wrong_scope = client.get(
            "/api/v1/agent-enrollments/verification",
            headers={"Authorization": f"Bearer {ENROLLMENT_TOKEN}"},
        )

    assert missing.status_code == 401
    assert wrong_scope.status_code == 401
    assert "sbe1." not in str(wrong_scope.json())


def test_exchange_forwards_a_reenrollment_target_only_when_explicitly_requested():
    with client_for(UserRole.OWNER) as client:
        response = client.post(
            "/api/v1/agent-enrollments/exchange",
            headers={
                "Authorization": f"Bearer {ENROLLMENT_TOKEN}",
                "X-SkyBeat-Reenroll-Device": "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0",
            },
        )

    assert response.status_code == 200
    assert (
        FakeEnrollmentService.last_expected_replacement_device_uuid
        == "65f5cbda-529a-4f75-8ef1-aef3c57a5ff0"
    )
