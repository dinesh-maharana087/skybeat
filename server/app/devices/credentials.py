"""High-entropy device token generation and verification."""

import base64
import binascii
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pydantic import SecretStr


class InvalidCredential(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid device credential.")


@dataclass(frozen=True)
class GeneratedCredential:
    credential_id: str
    token: SecretStr = field(repr=False)
    digest: bytes = field(repr=False)


@dataclass(frozen=True)
class ParsedCredential:
    credential_id: str
    secret: str = field(repr=False)


def generate_credential() -> GeneratedCredential:
    credential_id = str(uuid4())
    token = f"sb1.{credential_id}.{secrets.token_urlsafe(32)}"
    return GeneratedCredential(credential_id, SecretStr(token), hashlib.sha256(token.encode()).digest())


def parse_credential(token: str) -> ParsedCredential:
    if len(token) != 84:
        raise InvalidCredential()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "sb1":
        raise InvalidCredential()
    _, credential_id, secret = parts
    try:
        identifier = UUID(credential_id)
        raw = base64.b64decode(secret + "=", altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise InvalidCredential() from None
    if (
        str(identifier) != credential_id
        or identifier.version != 4
        or len(raw) != 32
        or base64.urlsafe_b64encode(raw).decode().rstrip("=") != secret
    ):
        raise InvalidCredential()
    return ParsedCredential(credential_id, secret)


def verify_token(token: str, expected_digest: bytes) -> bool:
    try:
        parse_credential(token)
    except InvalidCredential:
        return False
    return hmac.compare_digest(hashlib.sha256(token.encode("ascii")).digest(), expected_digest)
