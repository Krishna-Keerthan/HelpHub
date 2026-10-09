import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db import tenant_context
from app.db.tenant_context import set_tenant, tenant_transaction
from tests.conftest import MakeTenant, SeededTenant

CURRENT_TENANT = "SELECT current_setting('app.tenant_id', true)"


async def test_set_tenant_sets_value_for_current_transaction(
    app_conn: AsyncConnection,
) -> None:
    tenant_id = uuid.uuid4()
    session = AsyncSession(bind=app_conn)
    await set_tenant(session, tenant_id)

    result = await session.execute(text(CURRENT_TENANT))
    assert result.scalar_one() == str(tenant_id)
    await session.close()


async def test_set_tenant_does_not_outlive_the_transaction(
    app_conn: AsyncConnection,
) -> None:
    session = AsyncSession(bind=app_conn)
    await set_tenant(session, uuid.uuid4())
    await session.commit()

    result = await session.execute(text(CURRENT_TENANT))
    assert result.scalar_one() in (None, "")
    await session.close()


async def test_tenant_transaction_commits_and_scopes_rls(
    make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    email = f"new@{tenant['slug']}.test"

    async with tenant_transaction(tenant["id"]) as session:
        visible = (
            await session.execute(text("SELECT count(*) FROM users"))
        ).scalar_one()
        assert visible == 1  # only this tenant's seeded user
        await session.execute(
            text(
                "INSERT INTO users (tenant_id, email, password_hash, role) "
                "VALUES (:tid, :email, 'x', 'agent')"
            ),
            {"tid": tenant["id"], "email": email},
        )

    stored = await owner_conn.execute(
        text("SELECT count(*) FROM users WHERE email = :email"), {"email": email}
    )
    assert stored.scalar_one() == 1


async def test_tenant_transaction_rolls_back_and_reraises(
    make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    email = f"rolled-back@{tenant['slug']}.test"

    with pytest.raises(RuntimeError, match="boom"):
        async with tenant_transaction(tenant["id"]) as session:
            await session.execute(
                text(
                    "INSERT INTO users (tenant_id, email, password_hash, role) "
                    "VALUES (:tid, :email, 'x', 'agent')"
                ),
                {"tid": tenant["id"], "email": email},
            )
            raise RuntimeError("boom")

    stored = await owner_conn.execute(
        text("SELECT count(*) FROM users WHERE email = :email"), {"email": email}
    )
    assert stored.scalar_one() == 0


async def test_tenant_transaction_cannot_write_other_tenant(
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    a, b = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]

    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_transaction(a["id"]) as session:
            await session.execute(
                text(
                    "INSERT INTO users (tenant_id, email, password_hash, role) "
                    "VALUES (:tid, 'evil@example.com', 'x', 'agent')"
                ),
                {"tid": b["id"]},
            )


async def test_pooled_connection_does_not_leak_tenant_context(
    two_tenants_seeded: dict[str, SeededTenant], monkeypatch: pytest.MonkeyPatch
) -> None:
    a = two_tenants_seeded["tenant_a"]
    engine = create_async_engine(settings.database_url, pool_size=1, max_overflow=0)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(tenant_context, "AsyncSessionLocal", maker)
    try:
        async with tenant_transaction(a["id"]) as session:
            seen = (
                await session.execute(text("SELECT count(*) FROM users"))
            ).scalar_one()
            assert seen == 1

        # Same single pooled connection, no tenant context set.
        async with maker() as plain:
            leaked = (
                await plain.execute(text("SELECT count(*) FROM users"))
            ).scalar_one()
            setting = (await plain.execute(text(CURRENT_TENANT))).scalar_one()
        assert leaked == 0
        assert setting in (None, "")
    finally:
        await engine.dispose()
