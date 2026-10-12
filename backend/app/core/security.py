import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

REQUIRED_CLAIMS = ["exp", "sub", "tid"]

_password_hash = PasswordHash.recommended()


class InvalidTokenError(Exception):
    """Raised for any token that is malformed, expired, forged or incomplete.

    ``reason`` is a fixed, log-safe label (an exception class name or a fixed
    string); it never contains token content.
    """

    def __init__(self, message: str, reason: str = "invalid_token") -> None:
        super().__init__(message)
        self.reason = reason


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
        raise InvalidTokenError(str(exc), reason=type(exc).__name__) from exc


@dataclass(frozen=True)
class TokenSubject:
    user_id: uuid.UUID
    tenant_id: uuid.UUID


def _canonical_uuid(value: object) -> uuid.UUID:
    """Only the exact form we issue (str(uuid)): no ints, lists, urn:/braces."""
    if not isinstance(value, str):
        raise InvalidTokenError("claim is not a string", reason="invalid_claim")
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise InvalidTokenError("claim is not a UUID", reason="invalid_claim") from None
    if str(parsed) != value:
        raise InvalidTokenError("claim is not a canonical UUID", reason="invalid_claim")
    return parsed


def parse_token_subject(token: str) -> TokenSubject:
    """Decode ``token`` and return its user and tenant ids.

    The single place token claims are validated: any malformed, missing or
    mistyped ``sub``/``tid`` raises InvalidTokenError (callers answer 401).
    """
    claims = decode_access_token(token)
    return TokenSubject(
        user_id=_canonical_uuid(claims["sub"]),
        tenant_id=_canonical_uuid(claims["tid"]),
    )
