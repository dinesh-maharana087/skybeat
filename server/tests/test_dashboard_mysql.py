import asyncio
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.dashboard.auth import VerifiedIdentity
from app.dashboard.service import DashboardAuthService, SessionRejected
from app.db import database_utc
from app.main import create_app
from app.models import AdminSession, ApplicationUser, AuditEvent, Project
from app.users.service import UserRole

pytestmark = pytest.mark.mysql


class FakeOIDC:
    def __init__(self, identity: VerifiedIdentity) -> None:
        self.identity = identity
        self.last_nonce: str | None = None

    async def authorization_url(self, *, redirect_uri, state, nonce, code_verifier):
        assert redirect_uri == "https://monitor.example.test/auth/google/callback"
        assert state and nonce and code_verifier
        return "https://accounts.example.test/authorize"

    async def verify_callback(self, *, code, redirect_uri, nonce, code_verifier):
        assert code == "authorization-code"
        assert redirect_uri == "https://monitor.example.test/auth/google/callback"
        assert nonce and code_verifier
        self.last_nonce = nonce
        return self.identity


def auth_service(mysql_database, mysql_settings, identity):
    config = Settings(
        env="test",
        database_url=mysql_settings.database_url.get_secret_value(),
        allowed_emails=["ops@example.test"],
        session_encryption_key=Fernet.generate_key().decode("ascii"),
    )
    oidc = FakeOIDC(VerifiedIdentity("google-sub", "ops@example.test", True, None))
    with mysql_database.transaction() as session:
        now = database_utc(session)
        session.add(
            ApplicationUser(
                email="ops@example.test",
                display_name="Ops Owner",
                google_sub=None,
                role=UserRole.OWNER.value,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
    return DashboardAuthService(mysql_database, config, oidc), oidc


def test_authorized_google_identity_receives_opaque_session(
    mysql_database, mysql_settings, identity
):
    service, oidc = auth_service(mysql_database, mysql_settings, identity)
    login = asyncio.run(service.begin_login("https://monitor.example.test/auth/google/callback"))
    token = asyncio.run(
        service.complete_login(
            state=login.state,
            code="authorization-code",
            browser_binding=login.browser_binding,
            redirect_uri="https://monitor.example.test/auth/google/callback",
        )
    )

    user = service.authenticate_session(token)

    assert user.email == "ops@example.test"
    assert user.role is UserRole.OWNER
    assert oidc.last_nonce is not None
    with mysql_database.transaction() as session:
        stored = session.scalar(select(AdminSession))
        assert stored is not None
        assert stored.session_hash != token.encode()


def test_active_owner_creates_a_project_through_the_dashboard_api_with_audited_identity(
    mysql_database, mysql_settings, identity
):
    service, _ = auth_service(mysql_database, mysql_settings, identity)
    login = asyncio.run(service.begin_login("https://monitor.example.test/auth/google/callback"))
    token = asyncio.run(
        service.complete_login(
            state=login.state,
            code="authorization-code",
            browser_binding=login.browser_binding,
            redirect_uri="https://monitor.example.test/auth/google/callback",
        )
    )
    app = create_app(service.settings, database=mysql_database)
    app.state.dashboard_auth_service = service

    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("__Host-skybeat_session", token)
        response = client.post("/api/v1/projects", json={"name": "Owner dashboard project"})

    assert response.status_code == 200
    project_id = response.json()["project"]["project_id"]
    with mysql_database.transaction() as session:
        project = session.scalar(select(Project).where(Project.public_id == project_id))
        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "project.created",
                AuditEvent.actor == "ops@example.test",
            )
        )

    assert project is not None
    assert project.name == "Owner dashboard project"
    assert audit is not None
    assert audit.project_id == project.id


def test_unauthorized_or_empty_policy_identity_cannot_create_session(
    mysql_database, mysql_settings, identity
):
    service, _ = auth_service(mysql_database, mysql_settings, identity)
    service.settings.allowed_emails = ()
    login = asyncio.run(service.begin_login("https://monitor.example.test/auth/google/callback"))

    with pytest.raises(SessionRejected):
        asyncio.run(
            service.complete_login(
                state=login.state,
                code="authorization-code",
                browser_binding=login.browser_binding,
                redirect_uri="https://monitor.example.test/auth/google/callback",
            )
        )


def test_expired_logout_and_allowlist_removal_revoke_dashboard_access(
    mysql_database, mysql_settings, identity
):
    service, _ = auth_service(mysql_database, mysql_settings, identity)
    login = asyncio.run(service.begin_login("https://monitor.example.test/auth/google/callback"))
    token = asyncio.run(
        service.complete_login(
            state=login.state,
            code="authorization-code",
            browser_binding=login.browser_binding,
            redirect_uri="https://monitor.example.test/auth/google/callback",
        )
    )
    service.logout(token)
    with pytest.raises(SessionRejected):
        service.authenticate_session(token)

    login = asyncio.run(service.begin_login("https://monitor.example.test/auth/google/callback"))
    token = asyncio.run(
        service.complete_login(
            state=login.state,
            code="authorization-code",
            browser_binding=login.browser_binding,
            redirect_uri="https://monitor.example.test/auth/google/callback",
        )
    )
    service.settings.allowed_emails = ()
    with pytest.raises(SessionRejected):
        service.authenticate_session(token)
    with mysql_database.transaction() as session:
        stored = session.scalar(select(AdminSession).order_by(AdminSession.id.desc()))
        assert stored is not None and stored.revoked_at is not None

    service.settings.allowed_emails = ("ops@example.test",)
    login = asyncio.run(service.begin_login("https://monitor.example.test/auth/google/callback"))
    token = asyncio.run(
        service.complete_login(
            state=login.state,
            code="authorization-code",
            browser_binding=login.browser_binding,
            redirect_uri="https://monitor.example.test/auth/google/callback",
        )
    )
    with mysql_database.transaction() as session:
        stored = session.scalar(select(AdminSession).order_by(AdminSession.id.desc()))
        assert stored is not None
        stored.expires_at = database_utc(session) - timedelta(seconds=1)
    with pytest.raises(SessionRejected):
        service.authenticate_session(token)


def test_session_uses_current_durable_role_and_rejects_disabled_user(
    mysql_database, mysql_settings, identity
):
    service, _ = auth_service(mysql_database, mysql_settings, identity)
    login = asyncio.run(service.begin_login("https://monitor.example.test/auth/google/callback"))
    token = asyncio.run(
        service.complete_login(
            state=login.state,
            code="authorization-code",
            browser_binding=login.browser_binding,
            redirect_uri="https://monitor.example.test/auth/google/callback",
        )
    )
    with mysql_database.transaction() as session:
        user = session.scalar(
            select(ApplicationUser).where(ApplicationUser.email == "ops@example.test")
        )
        assert user is not None
        user.role = UserRole.USER.value

    assert service.authenticate_session(token).role is UserRole.USER

    with mysql_database.transaction() as session:
        user = session.scalar(
            select(ApplicationUser).where(ApplicationUser.email == "ops@example.test")
        )
        assert user is not None
        user.is_active = False

    with pytest.raises(SessionRejected):
        service.authenticate_session(token)
