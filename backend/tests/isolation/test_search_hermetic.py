"""ANN search on a vacuumed index: the HNSW path alone is correct.

used_fallback is False here, so a broken ANN path (for example a missing
hnsw.iterative_scan) cannot hide behind the exact fallback.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.repositories.chunks import (
    CHUNKS_EMBEDDING_INDEX,
    search_statement,
)
from app.db.tenant_context import set_tenant, tenant_transaction
from app.services.search import search_in_session
from tests.conftest import (
    SeededTenant,
    insert_chunk,
    insert_chunks,
    insert_document,
    unit_vector,
)
from tests.helpers.plans import explain_statement
from tests.isolation.ann_helpers import ensure_ann_reachable

Q = unit_vector(1.0)


async def _seed(owner_conn: AsyncConnection, ta: SeededTenant, tb: SeededTenant):
    """Spec layout: 200 B chunks right next to q, 3 A chunks far from it."""
    doc_a = await insert_document(owner_conn, ta["id"], created_by=ta["user_id"])
    doc_b = await insert_document(owner_conn, tb["id"], created_by=tb["user_id"])
    await insert_chunks(
        owner_conn,
        tb["id"],
        doc_b,
        [unit_vector(1.0, 0.001 * (i + 1)) for i in range(200)],
    )
    a_ids = {
        await insert_chunk(
            owner_conn,
            ta["id"],
            doc_a,
            chunk_index=i,
            embedding=unit_vector(0.0, 1.0, 0.1 * (i + 1)),
        )
        for i in range(3)
    }
    await owner_conn.commit()
    return a_ids


async def test_hnsw_path_finds_small_tenant_without_fallback(
    owner_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
    app_conn: AsyncConnection,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    a_ids = await _seed(owner_conn, ta, tb)
    await ensure_ann_reachable(owner_conn, list(a_ids), Q)

    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, ta["id"])
        # Test-only: pins the HNSW plan (see tests/isolation/conftest.py).
        await session.execute(text("SET LOCAL enable_sort = off"))
        plan = await session.execute(
            explain_statement(search_statement(ta["id"], Q, "", [], 3))
        )
        plan_text = "\n".join(row[0] for row in plan)
        result = await search_in_session(session, ta["id"], "", Q, 3)

    assert CHUNKS_EMBEDDING_INDEX in plan_text, plan_text
    assert {hit.chunk_id for hit in result.hits} == a_ids
    assert result.used_fallback is False


async def test_production_config_search_without_fallback(
    owner_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    a_ids = await _seed(owner_conn, ta, tb)

    async with tenant_transaction(ta["id"]) as session:
        result = await search_in_session(session, ta["id"], "", Q, 3)

    assert {hit.chunk_id for hit in result.hits} == a_ids
    assert result.used_fallback is False
