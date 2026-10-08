import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import Tenant, User


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


async def make_tenant(session: AsyncSession) -> Tenant:
    slug = f"t-{uuid.uuid4().hex[:12]}"
    tenant = Tenant(name=slug, slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


def make_user(tenant: Tenant, email: str) -> User:
    return User(tenant_id=tenant.id, email=email, password_hash="x", role="agent")


async def test_same_email_in_two_tenants_succeeds(db_session: AsyncSession) -> None:
    acme = await make_tenant(db_session)
    globex = await make_tenant(db_session)

    db_session.add_all(
        [make_user(acme, "sam@example.com"), make_user(globex, "sam@example.com")]
    )
    await db_session.flush()


async def test_duplicate_email_in_one_tenant_rejected(
    db_session: AsyncSession,
) -> None:
    acme = await make_tenant(db_session)
    db_session.add(make_user(acme, "sam@example.com"))
    await db_session.flush()

    db_session.add(make_user(acme, "sam@example.com"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_uppercase_email_rejected(db_session: AsyncSession) -> None:
    acme = await make_tenant(db_session)
    db_session.add(make_user(acme, "Sam@Example.com"))

    with pytest.raises(IntegrityError):
        await db_session.flush()
