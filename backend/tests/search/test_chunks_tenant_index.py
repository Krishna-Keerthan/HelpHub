"""Migration 0005: btree on chunks.tenant_id, used for small-tenant lookups."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.repositories.chunks import search_statement
from app.db.tenant_context import set_tenant
from tests.conftest import MakeTenant, insert_chunks, insert_document, unit_vector
from tests.helpers.plans import explain_statement


async def test_tenant_index_exists(owner_conn: AsyncConnection) -> None:
    result = await owner_conn.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
            "AND tablename = 'chunks' AND indexname = 'ix_chunks_tenant_id'"
        )
    )
    indexdef = result.scalar_one_or_none()
    assert indexdef is not None, "chunks lacks ix_chunks_tenant_id"
    assert "USING btree (tenant_id)" in indexdef


async def test_exact_search_uses_tenant_index(
    owner_conn: AsyncConnection, make_tenant: MakeTenant, app_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    doc = await insert_document(owner_conn, tenant["id"], created_by=tenant["user_id"])
    await insert_chunks(owner_conn, tenant["id"], doc, [unit_vector(1.0)] * 3)
    await owner_conn.commit()

    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, tenant["id"])
        # The table is tiny in tests, so a seq scan would otherwise be cheaper.
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = await session.execute(
            explain_statement(
                search_statement(tenant["id"], unit_vector(1.0), "", [], 3, exact=True)
            )
        )
        plan_text = "\n".join(row[0] for row in plan)

    assert "ix_chunks_tenant_id" in plan_text, plan_text
