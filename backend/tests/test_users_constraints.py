import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import Tenant, User
from app.db.tenant_context import set_tenant


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    # Runtime role, so tests see the same privileges as the app.
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()


def constraint_name(exc: IntegrityError) -> str | None:
    cause = exc.orig.__cause__ if exc.orig is not None else None
    return getattr(cause, "constraint_name", None)


async def add_tenant(session: AsyncSession) -> Tenant:
    slug = f"t-{uuid.uuid4().hex[:12]}"
    tenant = Tenant(name=slug, slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


def make_user(tenant: Tenant, email: str) -> User:
    return User(tenant_id=tenant.id, email=email, password_hash="x", role="agent")


async def add_user(session: AsyncSession, tenant: Tenant, email: str) -> None:
    """Insert a user under the tenant's RLS context and flush it."""
    await set_tenant(session, tenant.id)
    session.add(make_user(tenant, email))
    await session.flush()


async def test_same_email_in_two_tenants_succeeds(db_session: AsyncSession) -> None:
    acme = await add_tenant(db_session)
    globex = await add_tenant(db_session)

    await add_user(db_session, acme, "sam@example.com")
    await add_user(db_session, globex, "sam@example.com")

    for tenant in (acme, globex):
        await set_tenant(db_session, tenant.id)
        count = await db_session.execute(
            text("SELECT count(*) FROM users WHERE email = 'sam@example.com'")
        )
        assert count.scalar_one() == 1


async def test_duplicate_email_in_one_tenant_rejected(
    db_session: AsyncSession,
) -> None:
    acme = await add_tenant(db_session)
    await add_user(db_session, acme, "sam@example.com")

    with pytest.raises(IntegrityError) as exc_info:
        await add_user(db_session, acme, "sam@example.com")
    assert constraint_name(exc_info.value) == "uq_users_tenant_id_email"


async def test_uppercase_email_rejected(db_session: AsyncSession) -> None:
    acme = await add_tenant(db_session)

    with pytest.raises(IntegrityError) as exc_info:
        await add_user(db_session, acme, "Sam@Example.com")
    assert constraint_name(exc_info.value) == "ck_users_email_lowercase"
