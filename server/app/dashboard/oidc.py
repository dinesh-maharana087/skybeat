"""Maintained-library Google OIDC boundary; tokens never reach application storage."""

from collections.abc import Mapping
from typing import Protocol

from authlib.common.errors import AuthlibBaseError  # type: ignore[import-untyped]
from authlib.integrations.base_client.errors import OAuthError  # type: ignore[import-untyped]
from authlib.integrations.starlette_client import OAuth  # type: ignore[import-untyped]
from httpx import HTTPError

from app.dashboard.auth import VerifiedIdentity

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


class OIDCError(RuntimeError):
    """Safe authentication failure without provider details."""


class OIDCClient(Protocol):
    async def authorization_url(
        self, *, redirect_uri: str, state: str, nonce: str, code_verifier: str
    ) -> str: ...

    async def verify_callback(
        self, *, code: str, redirect_uri: str, nonce: str, code_verifier: str
    ) -> VerifiedIdentity: ...


class GoogleOIDCClient:
    """Google authorization-code client backed by Authlib's OIDC validation."""

    def __init__(
        self, client_id: str | None, client_secret: str | None, timeout_seconds: int
    ) -> None:
        self._configured = bool(client_id and client_secret)
        oauth = OAuth()
        self._client = oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=GOOGLE_DISCOVERY_URL,
            client_kwargs={
                "scope": "openid email",
                "code_challenge_method": "S256",
                "timeout": timeout_seconds,
            },
        )

    async def authorization_url(
        self, *, redirect_uri: str, state: str, nonce: str, code_verifier: str
    ) -> str:
        if not self._configured:
            raise OIDCError("Dashboard authentication is not configured.")
        try:
            result = await self._client.create_authorization_url(
                redirect_uri=redirect_uri,
                state=state,
                nonce=nonce,
                code_verifier=code_verifier,
            )
            url = result.get("url")
            if not isinstance(url, str):
                raise OIDCError("Google authorization response was invalid.")
            return url
        except (AuthlibBaseError, HTTPError, OAuthError, RuntimeError, ValueError) as error:
            raise OIDCError("Google authentication is temporarily unavailable.") from error

    async def verify_callback(
        self, *, code: str, redirect_uri: str, nonce: str, code_verifier: str
    ) -> VerifiedIdentity:
        if not self._configured or not code or len(code) > 4096:
            raise OIDCError("Google authentication failed.")
        try:
            token = await self._client.fetch_access_token(
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
            claims = await self._client.parse_id_token(token, nonce=nonce)
        except (AuthlibBaseError, HTTPError, OAuthError, RuntimeError, ValueError) as error:
            raise OIDCError("Google authentication failed.") from error
        return _identity_from_claims(claims)


def _identity_from_claims(claims: Mapping[str, object]) -> VerifiedIdentity:
    google_sub = claims.get("sub")
    email = claims.get("email")
    email_verified = claims.get("email_verified")
    hosted_domain = claims.get("hd")
    if (
        not isinstance(google_sub, str)
        or not 1 <= len(google_sub) <= 255
        or not isinstance(email, str)
        or not 3 <= len(email) <= 320
        or email_verified is not True
        or (hosted_domain is not None and not isinstance(hosted_domain, str))
    ):
        raise OIDCError("Google identity was incomplete.")
    return VerifiedIdentity(
        google_sub=google_sub,
        email=email.strip().lower(),
        email_verified=True,
        hosted_domain=hosted_domain.strip().lower() if hosted_domain else None,
    )
