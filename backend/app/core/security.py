import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

ACCESS_TYPE = "access"
REFRESH_TYPE = "refresh"
# "typ" keeps the two token kinds apart: each is accepted only where it is meant.
REQUIRED_CLAIMS = ["exp", "sub", "tid", "typ"]
REFRESH_REQUIRED_CLAIMS = [*REQUIRED_CLAIMS, "jti"]

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
    payload = {**claims, "typ": ACCESS_TYPE, "iat": now, "exp": now + expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: uuid.UUID, tenant_id: uuid.UUID, jti: uuid.UUID, expires_at: datetime
) -> str:
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "jti": str(jti),
        "typ": REFRESH_TYPE,
        "iat": datetime.now(UTC),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str, typ: str, required: list[str]) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": required},
        )
    except jwt.PyJWTError as exc:
        # gate-allow: str-exc stored in the exception, never logged (reason is logged)
        raise InvalidTokenError(str(exc), reason=type(exc).__name__) from exc
    if claims["typ"] != typ:
        raise InvalidTokenError("wrong token type", reason="wrong_token_type")
    return claims


def decode_access_token(token: str) -> dict[str, Any]:
    return _decode(token, ACCESS_TYPE, REQUIRED_CLAIMS)


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


@dataclass(frozen=True)
class RefreshClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    jti: uuid.UUID


def parse_refresh_token(token: str) -> RefreshClaims:
    """Verify signature, expiry and type, then return the ids. No database access.

    The tenant used for the lookup comes from this verified token only.
    """
    claims = _decode(token, REFRESH_TYPE, REFRESH_REQUIRED_CLAIMS)
    return RefreshClaims(
        user_id=_canonical_uuid(claims["sub"]),
        tenant_id=_canonical_uuid(claims["tid"]),
        jti=_canonical_uuid(claims["jti"]),
    )
