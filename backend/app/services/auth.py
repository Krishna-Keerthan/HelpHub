from app.core.config import settings
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.db.repositories import tenants as tenants_repo
from app.db.repositories import users as users_repo
from app.db.session import AsyncSessionLocal
from app.db.tenant_context import set_tenant
from app.schemas.auth import LoginRequest, RegisterRequest


class InvalidCredentials(Exception):
    """Login failed; deliberately gives no hint about which part was wrong."""


class RegistrationDisabled(Exception):
    pass


class TenantSlugTaken(Exception):
    pass


class ReservedSlug(Exception):
    """The slug is in a namespace reserved for internal tooling."""


RESERVED_SLUG_PREFIX = "eval-"


def issue_token(user: User) -> str:
    return create_access_token({"sub": str(user.id), "tid": str(user.tenant_id)})


async def register_tenant(
    data: RegisterRequest, *, reserved_ok: bool = False
) -> tuple[User, str]:
    """Public registration: refused unless ``allow_public_registration`` is on.

    ``reserved_ok`` is for the evaluation harness only; no API schema carries it.
    """
    if not settings.allow_public_registration:
        raise RegistrationDisabled
    return await create_tenant_with_admin(data, reserved_ok=reserved_ok)


async def create_tenant_with_admin(
    data: RegisterRequest, *, reserved_ok: bool = False
) -> tuple[User, str]:
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
    return user, issue_token(user)


async def authenticate(data: LoginRequest) -> str:
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
    return issue_token(user)
