import asyncio
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import Settings
from app.dashboard.auth import VerifiedIdentity
from app.dashboard.service import DashboardAuthService, SessionRejected
from app.db import database_utc
from app.models import AdminSession

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
    assert oidc.last_nonce is not None
    with mysql_database.transaction() as session:
        stored = session.scalar(select(AdminSession))
        assert stored is not None
        assert stored.session_hash != token.encode()


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
