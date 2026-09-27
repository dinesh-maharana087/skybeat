from contextlib import contextmanager
from datetime import UTC, datetime

from app.config import Settings
from app.dashboard.auth import AuthorizationPolicy, VerifiedIdentity, session_token_digest
from app.dashboard.service import DashboardAuthService
from app.models import AdminSession, AuditEvent, OAuthTransaction


def test_authorization_policy_requires_verified_identity_and_server_controlled_match():
    policy = AuthorizationPolicy(
        allowed_emails=("ops@example.test",), allowed_domains=("trusted.example",)
    )

    assert policy.allows(
        VerifiedIdentity(
            google_sub="google-123",
            email="OPS@example.test",
            email_verified=True,
            hosted_domain=None,
        )
    )
    assert policy.allows(
        VerifiedIdentity(
            google_sub="google-456",
            email="person@unrelated.example",
            email_verified=True,
            hosted_domain="trusted.example",
        )
    )
    assert not policy.allows(
        VerifiedIdentity(
            google_sub="google-789",
            email="person@trusted.example",
            email_verified=True,
            hosted_domain=None,
        )
    )
    assert not policy.allows(
        VerifiedIdentity(
            google_sub="google-123",
            email="ops@example.test",
            email_verified=False,
            hosted_domain=None,
        )
    )


def test_authorization_policy_denies_when_no_email_or_verified_hosted_domain_matches():
    policy = AuthorizationPolicy(allowed_emails=(), allowed_domains=())

    assert not policy.allows(
        VerifiedIdentity(
            google_sub="google-123",
            email="ops@example.test",
            email_verified=True,
            hosted_domain="example.test",
        )
    )


def test_session_and_oauth_tables_store_only_digests_for_browser_secrets():
    session_columns = {column.name for column in AdminSession.__table__.columns}
    transaction_columns = {column.name for column in OAuthTransaction.__table__.columns}

    assert {"session_hash", "google_sub", "expires_at", "last_used_at", "revoked_at"} <= (
        session_columns
    )
    assert {"state_hash", "nonce_hash", "browser_binding_hash", "expires_at", "consumed_at"} <= (
        transaction_columns
    )
    assert "session_token" not in session_columns
    assert "state" not in transaction_columns
    assert "nonce" not in transaction_columns


def test_session_digest_is_stable_and_never_equals_the_raw_browser_token():
    token = "opaque-browser-token"

    assert session_token_digest(token) == session_token_digest(token)
    assert session_token_digest(token) != token.encode()


def test_successful_google_login_creates_a_safe_audit_event():
    added: list[object] = []

    class Result:
        def scalar_one(self):
            return datetime(2026, 9, 27, tzinfo=UTC)

    class Session:
        def execute(self, statement):
            return Result()

        def add(self, item):
            added.append(item)

    class Database:
        @contextmanager
        def transaction(self):
            yield Session()

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test"
    )
    service = DashboardAuthService(Database(), settings, object())

    service._issue_session(VerifiedIdentity("google-123", "ops@example.test", True, None))

    audit = next(item for item in added if isinstance(item, AuditEvent))
    assert audit.actor == "ops@example.test"
    assert audit.action == "auth.login_succeeded"
    assert "token" not in audit.details


def test_logout_creates_a_safe_audit_event():
    added: list[object] = []

    class Result:
        def scalar_one(self):
            return datetime(2026, 9, 27, tzinfo=UTC)

    class Session:
        def __init__(self):
            self.stored = AdminSession(
                session_hash=session_token_digest("opaque-browser-token"),
                google_sub="google-123",
                email="ops@example.test",
                hosted_domain=None,
                issued_at=datetime(2026, 9, 27, tzinfo=UTC),
                expires_at=datetime(2026, 9, 28, tzinfo=UTC),
                last_used_at=datetime(2026, 9, 27, tzinfo=UTC),
                revoked_at=None,
                authorization_policy_version=1,
            )

        def execute(self, statement):
            return Result()

        def scalar(self, statement):
            return self.stored

        def add(self, item):
            added.append(item)

    class Database:
        @contextmanager
        def transaction(self):
            yield Session()

    settings = Settings(
        env="test", database_url="mysql+pymysql://test:example@127.0.0.1/skybeat_test"
    )
    service = DashboardAuthService(Database(), settings, object())

    service.logout("opaque-browser-token")

    audit = next(item for item in added if isinstance(item, AuditEvent))
    assert audit.actor == "ops@example.test"
    assert audit.action == "auth.logout"
    assert "session" not in audit.details
