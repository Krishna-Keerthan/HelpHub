import base64
import json
from datetime import timedelta
from typing import Any

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    DUMMY_HASH,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

CLAIMS = {"sub": "user-1", "tid": "tenant-1", "role": "admin"}


def _b64(data: dict[str, Any]) -> str:
    raw = json.dumps(data).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _other_algorithm() -> str:
    return "HS512" if settings.jwt_algorithm != "HS512" else "HS384"


def test_password_hashing() -> None:
    raw_password = "SecurePassword123"
    hashed = hash_password(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_hashes_are_salted() -> None:
    assert hash_password("SecurePassword123") != hash_password("SecurePassword123")


def test_dummy_hash_never_verifies_and_matches_real_parameters() -> None:
    assert verify_password("anything", DUMMY_HASH) is False
    # "$argon2id$v=19$m=...,t=...,p=...$salt$hash": same cost parameters.
    assert DUMMY_HASH.split("$")[1:4] == hash_password("x").split("$")[1:4]


def test_jwt_round_trip() -> None:
    token = create_access_token(CLAIMS)
    decoded = decode_access_token(token)

    assert decoded["sub"] == CLAIMS["sub"]
    assert decoded["tid"] == CLAIMS["tid"]
    assert decoded["role"] == CLAIMS["role"]
    assert "exp" in decoded


def test_expired_token_rejected() -> None:
    token = create_access_token(CLAIMS, expires_delta=timedelta(seconds=-10))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_tampered_signature_rejected() -> None:
    token = create_access_token(CLAIMS)
    header, payload, signature = token.split(".")
    flipped = "A" if signature[0] != "A" else "B"
    tampered = ".".join([header, payload, flipped + signature[1:]])

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_tampered_payload_rejected() -> None:
    token = create_access_token(CLAIMS)
    header, _, signature = token.split(".")
    forged = _b64({**CLAIMS, "tid": "tenant-2", "exp": 4102444800})

    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{header}.{forged}.{signature}")


def test_wrong_secret_rejected() -> None:
    token = jwt.encode(
        {**CLAIMS, "exp": 4102444800},
        "not-the-real-secret-not-the-real-secret",
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_token_with_alg_none_rejected() -> None:
    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({**CLAIMS, "exp": 4102444800})

    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{header}.{payload}.")


def test_token_signed_with_other_algorithm_rejected() -> None:
    token = jwt.encode(
        {**CLAIMS, "exp": 4102444800},
        settings.jwt_secret,
        algorithm=_other_algorithm(),
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


@pytest.mark.parametrize("missing", ["exp", "sub", "tid"])
def test_token_missing_required_claim_rejected(missing: str) -> None:
    claims = {**CLAIMS, "exp": 4102444800}
    del claims[missing]
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_garbage_token_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.jwt")
