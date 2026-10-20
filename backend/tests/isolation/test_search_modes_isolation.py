"""Every search mode, including tsvector-only and vector-only, stays inside the tenant."""

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.repositories.chunks import SearchMode
from app.db.tenant_context import set_tenant
from app.services.search import search_in_session
from tests.conftest import (
    SeededTenant,
    insert_chunk,
    insert_document,
    unit_vector,
)

Q = unit_vector(1.0)
WORD = "zanzibar"


async def _seed(owner_conn: AsyncConnection, tenant: SeededTenant) -> set[object]:
    doc = await insert_document(owner_conn, tenant["id"], created_by=tenant["user_id"])
    ids = {
        await insert_chunk(
            owner_conn,
            tenant["id"],
            doc,
            chunk_index=i,
            content=f"{WORD} {i}",
            embedding=Q,
        )
        for i in range(3)
    }
    await owner_conn.commit()
    return ids


@pytest.mark.parametrize("mode", ["hybrid", "vector", "keyword"])
async def test_no_mode_returns_another_tenants_chunk(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
    mode: SearchMode,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    a_ids = await _seed(owner_conn, ta)
    b_ids = await _seed(owner_conn, tb)  # same words, same vectors

    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, ta["id"])
        result = await search_in_session(
            session, ta["id"], WORD, None if mode == "keyword" else Q, 10, mode
        )

    found = {h.chunk_id for h in result.hits}
    assert found == a_ids  # a's own chunks are found, so the check is not vacuous
    assert not found & b_ids
