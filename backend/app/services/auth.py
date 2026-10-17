import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.principal import Principal
from app.core.security import (
    DUMMY_HASH,
    InvalidTokenError,
    RefreshClaims,
    create_access_token,
    create_refresh_token,
    hash_password,
    parse_refresh_token,
    verify_password,
)
from app.db.models import User
from app.db.repositories import refresh_tokens as refresh_repo
from app.db.repositories import tenants as tenants_repo
from app.db.repositories import users as users_repo
from app.db.session import AsyncSessionLocal, DbSession
from app.db.tenant_context import set_tenant, tenant_transaction
from app.schemas.auth import LoginRequest, RegisterRequest

logger = logging.getLogger(__name__)


class InvalidCredentials(Exception):
    """Login failed; deliberately gives no hint about which part was wrong."""


class RegistrationDisabled(Exception):
    pass


class TenantSlugTaken(Exception):
    pass


class ReservedSlug(Exception):
    """The slug is in a namespace reserved for internal tooling."""


RESERVED_SLUG_PREFIX = "eval-"


class InvalidRefreshToken(Exception):
    """The refresh token is unusable. ``reason`` is a fixed, log-safe label."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


def _access_token(user: User) -> str:
    return create_access_token({"sub": str(user.id), "tid": str(user.tenant_id)})


async def _add_refresh_token(
    session: DbSession, user: User, family_id: uuid.UUID
) -> str:
    jti = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_days)
    await refresh_repo.add(session, user.tenant_id, user.id, jti, family_id, expires_at)
    return create_refresh_token(user.id, user.tenant_id, jti, expires_at)


async def issue_tokens(user: User) -> TokenPair:
    """A new login: a new token family. Expired rows of the tenant are purged."""
    async with tenant_transaction(user.tenant_id) as session:
        await refresh_repo.delete_expired(session, user.tenant_id)
        refresh = await _add_refresh_token(session, user, uuid.uuid4())
    return TokenPair(_access_token(user), refresh)


async def register_tenant(
    data: RegisterRequest, *, reserved_ok: bool = False
) -> tuple[User, TokenPair]:
    """Public registration: refused unless ``allow_public_registration`` is on.

    ``reserved_ok`` is for the evaluation harness only; no API schema carries it.
    """
    if not settings.allow_public_registration:
        raise RegistrationDisabled
    user = await create_tenant_with_admin(data, reserved_ok=reserved_ok)
    return user, await issue_tokens(user)


async def create_tenant_with_admin(
    data: RegisterRequest, *, reserved_ok: bool = False
) -> User:
    """Create a tenant and its first admin; does not look at the registration flag.

    Used by public registration (after its flag check) and by the owner's
    scripts/seed_tenant.py.
    """
    if data.tenant_slug.startswith(RESERVED_SLUG_PREFIX) and not reserved_ok:
        raise ReservedSlug

    password_hash = hash_password(data.password)
    async with AsyncSessionLocal() as session:
        try:
            if await tenants_repo.get_by_slug(session, data.tenant_slug):
                raise TenantSlugTaken
            tenant = await tenants_repo.create(
                session, name=data.tenant_name, slug=data.tenant_slug
            )
            # Tenant context must follow the tenant insert and precede the user
            # insert; there is no commit in between, so it stays in effect.
            await set_tenant(session, tenant.id)
            user = await users_repo.create(
                session,
                tenant.id,
                email=data.email,
                password_hash=password_hash,
                role="admin",
            )
            await session.commit()
        except tenants_repo.SlugTaken as exc:
            await session.rollback()
            raise TenantSlugTaken from exc
        except BaseException:
            await session.rollback()
            raise
    return user


async def authenticate(data: LoginRequest) -> TokenPair:
    async with AsyncSessionLocal() as session:
        user: User | None = None
        tenant = await tenants_repo.get_by_slug(session, data.tenant_slug)
        if tenant is not None:
            await set_tenant(session, tenant.id)
            user = await users_repo.get_by_email(session, tenant.id, data.email)

    if user is None or not user.is_active:
        # Same Argon2 work as a real check, and the same error either way.
        verify_password(data.password, DUMMY_HASH)
        raise InvalidCredentials
    if not verify_password(data.password, user.password_hash):
        raise InvalidCredentials
    return await issue_tokens(user)


def _parse_refresh(refresh_token: str) -> RefreshClaims:
    try:
        return parse_refresh_token(refresh_token)
    except InvalidTokenError as exc:
        raise InvalidRefreshToken(exc.reason) from None


async def refresh(refresh_token: str) -> TokenPair:
    """Rotate: mark the presented token used and issue a new pair in its family.

    Verified (signature, expiry, type) before any database access; the tenant
    comes from the verified token only. A token that was already used means
    theft or a replay, so its whole family is revoked. The state changes commit
    before the failure is raised.
    """
    claims = _parse_refresh(refresh_token)
    pair: TokenPair | None = None
    failure = ""
    async with tenant_transaction(claims.tenant_id) as session:
        row = await refresh_repo.get_for_update(session, claims.tenant_id, claims.jti)
        if row is None or row.user_id != claims.user_id:
            failure = "unknown_token"
        elif row.revoked_at is not None:
            failure = "revoked"
        elif row.used_at is not None:
            await refresh_repo.revoke_family(session, claims.tenant_id, row.family_id)
            failure = "reuse_detected"
            logger.warning(
                "refresh token reuse: tenant=%s user=%s family=%s",
                claims.tenant_id,
                claims.user_id,
                row.family_id,
            )
        elif row.expires_at <= datetime.now(UTC):
            failure = "expired"
        else:
            user = await users_repo.get_by_id(session, claims.tenant_id, claims.user_id)
            if user is None or not user.is_active:
                await refresh_repo.revoke_family(
                    session, claims.tenant_id, row.family_id
                )
                failure = "user_unavailable"
            else:
                await refresh_repo.mark_used(session, claims.tenant_id, row.jti)
                new_refresh = await _add_refresh_token(session, user, row.family_id)
                pair = TokenPair(_access_token(user), new_refresh)
        await refresh_repo.delete_expired(session, claims.tenant_id)
    if pair is None:
        raise InvalidRefreshToken(failure)
    return pair


async def logout(principal: Principal, refresh_token: str) -> None:
    """Revoke the whole family of ``refresh_token``, which must be the caller's own."""
    claims = _parse_refresh(refresh_token)
    if claims.user_id != principal.user_id or claims.tenant_id != principal.tenant_id:
        raise InvalidRefreshToken("not_owner")
    async with tenant_transaction(principal.tenant_id) as session:
        row = await refresh_repo.get_for_update(
            session, principal.tenant_id, claims.jti
        )
        if row is not None and row.user_id == principal.user_id:
            await refresh_repo.revoke_family(
                session, principal.tenant_id, row.family_id
            )
