import asyncio
import secrets
import uuid
import weakref
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

ACCESS_TYPE = "access"
REFRESH_TYPE = "refresh"
# "typ" keeps the two token kinds apart: each is accepted only where it is meant.
REQUIRED_CLAIMS = ["exp", "sub", "tid", "typ"]
REFRESH_REQUIRED_CLAIMS = [*REQUIRED_CLAIMS, "jti"]

# OWASP's minimum Argon2id configuration (m=19 MiB, t=2, p=1). The parameters
# are stored in every hash, so hashes made with the library defaults
# (m=64 MiB, t=3, p=4) still verify; they are not rehashed on login.
ARGON2_MEMORY_KIB = 19456
ARGON2_TIME_COST = 2
ARGON2_PARALLELISM = 1
_password_hash = PasswordHash(
    (
        Argon2Hasher(
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_KIB,
            parallelism=ARGON2_PARALLELISM,
        ),
    )
)


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


# One hash at a time per event loop: each Argon2 run holds its memory until it
# finishes, so concurrent runs would add up. Running in a thread keeps the loop
# free while a hash is computed (and while others wait for the slot).
_hash_slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


def _hash_slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _hash_slots:
        _hash_slots[loop] = asyncio.Semaphore(1)
    return _hash_slots[loop]


async def hash_password_async(password: str) -> str:
    async with _hash_slot():
        return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, hashed: str) -> bool:
    async with _hash_slot():
        return await asyncio.to_thread(verify_password, password, hashed)


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
