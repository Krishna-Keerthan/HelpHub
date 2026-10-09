import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

REQUIRED_CLAIMS = ["exp", "sub", "tid"]

_password_hash = PasswordHash.recommended()


class InvalidTokenError(Exception):
    """Raised for any token that is malformed, expired, forged or incomplete."""


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


# Verified against when a login names an unknown tenant or user, so failures
# cost the same Argon2 work as a real password check.
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def create_access_token(
    claims: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    now = datetime.now(UTC)
    expires = expires_delta or timedelta(minutes=settings.access_token_minutes)
    payload = {**claims, "iat": now, "exp": now + expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
