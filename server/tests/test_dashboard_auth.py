from app.dashboard.auth import AuthorizationPolicy, VerifiedIdentity, session_token_digest
from app.models import AdminSession, OAuthTransaction


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
