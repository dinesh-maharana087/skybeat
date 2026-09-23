"""Authorization policy for verified Google OIDC identities."""

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class VerifiedIdentity:
    """Identity claims accepted only after OIDC library validation."""

    google_sub: str
    email: str
    email_verified: bool
    hosted_domain: str | None


@dataclass(frozen=True)
class AuthorizationPolicy:
    """Explicit server-controlled dashboard authorization policy."""

    allowed_emails: tuple[str, ...]
    allowed_domains: tuple[str, ...]

    def allows(self, identity: VerifiedIdentity) -> bool:
        if not identity.email_verified:
            return False
        if identity.email.lower() in self.allowed_emails:
            return True
        return (
            identity.hosted_domain is not None
            and identity.hosted_domain.lower() in self.allowed_domains
        )


def session_token_digest(token: str) -> bytes:
    """Return the only browser-session representation stored by the server."""
    return sha256(token.encode("ascii")).digest()
