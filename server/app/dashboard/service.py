"""Durable OAuth transactions and opaque application session lifecycle."""

import secrets
from dataclasses import dataclass
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.config import Settings
from app.dashboard.auth import AuthorizationPolicy, VerifiedIdentity, session_token_digest
from app.dashboard.oidc import OIDCClient, OIDCError
from app.db import Database, database_utc
from app.models import AdminSession, OAuthTransaction

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
            return DashboardUser(identity.google_sub, identity.email, identity.hosted_domain)

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
        return token
