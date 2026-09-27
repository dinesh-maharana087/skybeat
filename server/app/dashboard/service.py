"""Durable OAuth transactions and opaque application session lifecycle."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dashboard.auth import AuthorizationPolicy, VerifiedIdentity, session_token_digest
from app.dashboard.oidc import OIDCClient, OIDCError
from app.db import Database, database_utc
from app.models import AdminSession, ApplicationUser, AuditEvent, OAuthTransaction
from app.users.service import UserRole, normalize_email

OAUTH_TRANSACTION_LIFETIME = timedelta(minutes=10)
SESSION_ABSOLUTE_LIFETIME = timedelta(hours=8)
SESSION_IDLE_LIFETIME = timedelta(minutes=30)


class DashboardAuthError(RuntimeError):
    """Safe dashboard authentication failure."""


class SessionRejected(DashboardAuthError):
    """No usable authorized browser session exists."""


@dataclass(frozen=True)
class LoginRedirect:
    url: str
    browser_binding: str
    state: str


@dataclass(frozen=True)
class DashboardUser:
    google_sub: str
    email: str
    hosted_domain: str | None
    user_id: int = 0
    role: UserRole = UserRole.OWNER


LOCAL_DEVELOPMENT_DASHBOARD_USER = DashboardUser(
    google_sub="local-development",
    email="local-development@skybeat.invalid",
    hosted_domain=None,
    role=UserRole.OWNER,
)


def resolve_dashboard_user(
    settings: Settings, service: "DashboardAuthService", token: str | None
) -> DashboardUser:
    if settings.dev_auth_bypass:
        return LOCAL_DEVELOPMENT_DASHBOARD_USER
    if token is None:
        raise SessionRejected("Dashboard session is invalid.")
    return service.authenticate_session(token)


class DashboardAuthService:
    def __init__(self, database: Database, settings: Settings, oidc_client: OIDCClient) -> None:
        self.database = database
        self.settings = settings
        self.oidc_client = oidc_client
        secret = settings.session_encryption_key
        if secret is None:
            self._fernet = None
        else:
            try:
                self._fernet = Fernet(secret.get_secret_value().encode("ascii"))
            except (TypeError, ValueError) as error:
                raise DashboardAuthError("Dashboard session encryption is invalid.") from error

    @property
    def policy(self) -> AuthorizationPolicy:
        return AuthorizationPolicy(self.settings.allowed_emails, self.settings.allowed_domains)

    async def begin_login(self, redirect_uri: str) -> LoginRedirect:
        state, nonce, binding, verifier = self._create_transaction()
        try:
            url = await self.oidc_client.authorization_url(
                redirect_uri=redirect_uri, state=state, nonce=nonce, code_verifier=verifier
            )
        except OIDCError as error:
            raise DashboardAuthError("Google authentication is temporarily unavailable.") from error
        return LoginRedirect(url=url, browser_binding=binding, state=state)

    async def complete_login(
        self, *, state: str, code: str, browser_binding: str, redirect_uri: str
    ) -> str:
        nonce, verifier = self._consume_transaction(state, browser_binding)
        try:
            identity = await self.oidc_client.verify_callback(
                code=code, redirect_uri=redirect_uri, nonce=nonce, code_verifier=verifier
            )
        except OIDCError as error:
            raise DashboardAuthError("Google authentication failed.") from error
        if not self.policy.allows(identity):
            raise SessionRejected("Dashboard access is not authorized.")
        self._resolve_application_user(identity)
        return self._issue_session(identity)

    def authenticate_session(self, token: str) -> DashboardUser:
        if not token or len(token) > 256:
            raise SessionRejected("Dashboard session is invalid.")
        with self.database.transaction() as session:
            now = database_utc(session)
            stored = session.scalar(
                select(AdminSession)
                .where(AdminSession.session_hash == session_token_digest(token))
                .with_for_update()
            )
            if (
                stored is None
                or stored.revoked_at is not None
                or stored.expires_at <= now
                or stored.last_used_at + SESSION_IDLE_LIFETIME <= now
            ):
                raise SessionRejected("Dashboard session is expired.")
            identity = VerifiedIdentity(
                google_sub=stored.google_sub,
                email=stored.email,
                email_verified=True,
                hosted_domain=stored.hosted_domain,
            )
            if not self.policy.allows(identity):
                stored.revoked_at = now
                raise SessionRejected("Dashboard access is no longer authorized.")
            stored.last_used_at = now
            return self._resolve_application_user_in_session(session, identity, now)

    def logout(self, token: str) -> None:
        if not token or len(token) > 256:
            raise SessionRejected("Dashboard session is invalid.")
        with self.database.transaction() as session:
            now = database_utc(session)
            stored = session.scalar(
                select(AdminSession)
                .where(AdminSession.session_hash == session_token_digest(token))
                .with_for_update()
            )
            if stored is None or stored.revoked_at is not None or stored.expires_at <= now:
                raise SessionRejected("Dashboard session is invalid.")
            stored.revoked_at = now
            session.add(
                AuditEvent(
                    actor=stored.email,
                    action="auth.logout",
                    project_id=None,
                    device_id=None,
                    occurred_at=now,
                    details={"scope": "local_session"},
                )
            )

    def _create_transaction(self) -> tuple[str, str, str, str]:
        if self._fernet is None:
            raise DashboardAuthError("Dashboard authentication is not configured.")
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        browser_binding = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        with self.database.transaction() as session:
            now = database_utc(session)
            session.add(
                OAuthTransaction(
                    state_hash=session_token_digest(state),
                    nonce_hash=session_token_digest(nonce),
                    nonce_ciphertext=self._fernet.encrypt(nonce.encode("ascii")),
                    browser_binding_hash=session_token_digest(browser_binding),
                    pkce_verifier_ciphertext=self._fernet.encrypt(verifier.encode("ascii")),
                    created_at=now,
                    expires_at=now + OAUTH_TRANSACTION_LIFETIME,
                )
            )
        return state, nonce, browser_binding, verifier

    def _consume_transaction(self, state: str, browser_binding: str) -> tuple[str, str]:
        if (
            not state
            or not browser_binding
            or len(state) > 256
            or len(browser_binding) > 256
            or self._fernet is None
        ):
            raise DashboardAuthError("Google login could not be verified.")
        with self.database.transaction() as session:
            now = database_utc(session)
            transaction = session.scalar(
                select(OAuthTransaction)
                .where(OAuthTransaction.state_hash == session_token_digest(state))
                .with_for_update()
            )
            if (
                transaction is None
                or transaction.consumed_at is not None
                or transaction.expires_at <= now
                or not secrets.compare_digest(
                    transaction.browser_binding_hash, session_token_digest(browser_binding)
                )
            ):
                raise DashboardAuthError("Google login could not be verified.")
            transaction.consumed_at = now
            try:
                verifier = self._fernet.decrypt(transaction.pkce_verifier_ciphertext).decode(
                    "ascii"
                )
                nonce = self._fernet.decrypt(transaction.nonce_ciphertext).decode("ascii")
            except (InvalidToken, UnicodeDecodeError) as error:
                raise DashboardAuthError("Google login could not be verified.") from error
            if not secrets.compare_digest(transaction.nonce_hash, session_token_digest(nonce)):
                raise DashboardAuthError("Google login could not be verified.")
            return nonce, verifier

    def _issue_session(self, identity: VerifiedIdentity) -> str:
        token = secrets.token_urlsafe(32)
        with self.database.transaction() as session:
            now = database_utc(session)
            session.add(
                AdminSession(
                    session_hash=session_token_digest(token),
                    google_sub=identity.google_sub,
                    email=identity.email,
                    hosted_domain=identity.hosted_domain,
                    issued_at=now,
                    expires_at=now + SESSION_ABSOLUTE_LIFETIME,
                    last_used_at=now,
                    authorization_policy_version=1,
                )
            )
            session.add(
                AuditEvent(
                    actor=identity.email,
                    action="auth.login_succeeded",
                    project_id=None,
                    device_id=None,
                    occurred_at=now,
                    details={"authenticator": "google"},
                )
            )
        return token

    def _resolve_application_user(self, identity: VerifiedIdentity) -> DashboardUser:
        with self.database.transaction() as session:
            return self._resolve_application_user_in_session(
                session, identity, database_utc(session)
            )

    def _resolve_application_user_in_session(
        self, session: Session, identity: VerifiedIdentity, now: datetime
    ) -> DashboardUser:
        user = session.scalar(
            select(ApplicationUser)
            .where(ApplicationUser.email == normalize_email(identity.email))
            .with_for_update()
        )
        if user is None or not user.is_active:
            raise SessionRejected("Dashboard access has not been provisioned.")
        if user.google_sub is not None and not secrets.compare_digest(
            user.google_sub, identity.google_sub
        ):
            raise SessionRejected("Dashboard identity does not match the provisioned account.")
        if user.google_sub is None:
            user.google_sub = identity.google_sub
            user.updated_at = now
        try:
            role = UserRole(user.role)
        except ValueError as error:
            raise SessionRejected("Dashboard role is invalid.") from error
        return DashboardUser(identity.google_sub, user.email, identity.hosted_domain, user.id, role)
