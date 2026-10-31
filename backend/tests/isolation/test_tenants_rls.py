"""tenants has RLS with explicit helphub_app policies for exactly SELECT and INSERT."""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.repositories import tenants as tenants_repo
from app.db.session import AsyncSessionLocal
from tests.conftest import MakeTenant, _delete_tenants


async def test_app_role_inserts_and_selects_tenant_through_repository() -> None:
    slug = f"rls-{uuid.uuid4().hex[:10]}"
    tenant_id: uuid.UUID | None = None
    try:
        async with AsyncSessionLocal() as session:
            tenant = await tenants_repo.create(session, name="Rls", slug=slug)
            tenant_id = tenant.id  # INSERT ... RETURNING needs the SELECT policy
            await session.commit()
        async with AsyncSessionLocal() as session:
            found = await tenants_repo.get_by_slug(session, slug)
        assert found is not None and found.id == tenant_id
    finally:
        if tenant_id is not None:
            assert await _delete_tenants([tenant_id]) == {}


async def test_app_role_cannot_update_or_delete_tenants(
    app_conn: AsyncConnection, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    updated = await app_conn.execute(
        text("UPDATE tenants SET name = 'x' WHERE id = :id"), {"id": tenant["id"]}
    )
    deleted = await app_conn.execute(
        text("DELETE FROM tenants WHERE id = :id"), {"id": tenant["id"]}
    )
    assert (updated.rowcount, deleted.rowcount) == (0, 0)  # no policy: no rows visible
    await app_conn.rollback()
    still = await owner_conn.execute(
        text("SELECT count(*) FROM tenants WHERE id = :id"), {"id": tenant["id"]}
    )
    assert still.scalar_one() == 1


async def test_rls_is_enabled_not_forced(owner_conn: AsyncConnection) -> None:
    row = await owner_conn.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid = 'public.tenants'::regclass"
        )
    )
    assert row.one() == (True, False)
