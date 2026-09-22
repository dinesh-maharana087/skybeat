import hashlib
import secrets
from uuid import UUID, uuid4

import pytest

from app.devices.credentials import (
    InvalidCredential,
    generate_credential,
    parse_credential,
    verify_token,
)


def test_credential_has_independent_identifier_and_256_bit_secret():
    first = generate_credential()
    second = generate_credential()
    parsed = parse_credential(first.token.get_secret_value())
    assert UUID(parsed.credential_id).version == 4
    assert len(parsed.secret) == 43
    assert first.credential_id == parsed.credential_id
    assert first.digest == hashlib.sha256(first.token.get_secret_value().encode("ascii")).digest()
    assert first.digest != second.digest
    assert first.credential_id != second.credential_id
    assert first.token.get_secret_value() not in repr(first)


def test_verification_compares_complete_canonical_token():
    credential = generate_credential()
    token = credential.token.get_secret_value()
    assert verify_token(token, credential.digest)
    assert not verify_token(f"sb1.{uuid4()}.{parse_credential(token).secret}", credential.digest)
    assert not verify_token(token, secrets.token_bytes(32))


@pytest.mark.parametrize(
    "token",
    [
        "",
        "Bearer sb1.bad.secret",
        "sb2.id.secret",
        "sb1.bad.secret",
        f"sb1.{uuid4()}.short",
        f"sb1.{uuid4()}.{'a' * 44}",
        f"sb1.{uuid4()}.{'!' * 43}",
        "sb1." + "a" * 2000,
    ],
)
def test_bad_credentials_fail_without_echo(token):
    with pytest.raises(InvalidCredential) as error:
        parse_credential(token)
    assert str(error.value) == "Invalid device credential."


def test_identifier_must_be_canonical_lowercase_uuid():
    credential = generate_credential()
    token = credential.token.get_secret_value()
    with pytest.raises(InvalidCredential):
        parse_credential(token.replace(credential.credential_id, credential.credential_id.upper()))
