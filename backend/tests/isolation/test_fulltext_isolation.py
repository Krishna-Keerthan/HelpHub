"""The full-text branch never returns another tenant's chunk."""

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.tenant_context import set_tenant
from app.services.search import search_in_session
from tests.conftest import (
    SeededTenant,
    insert_chunk,
    insert_document,
    unit_vector,
)

Q = unit_vector(1.0)
FAR = unit_vector(0.0, 1.0)


async def _hits(app_conn: AsyncConnection, tenant: SeededTenant, query: str):
    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, tenant["id"])
        result = await search_in_session(session, tenant["id"], query, Q, 10)
    return result.hits


async def test_text_match_in_another_tenant_is_not_returned(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_a = await insert_document(owner_conn, ta["id"], created_by=ta["user_id"])
    doc_b = await insert_document(owner_conn, tb["id"], created_by=tb["user_id"])
    a_chunk = await insert_chunk(
        owner_conn, ta["id"], doc_a, content="plain note", embedding=FAR
    )
    b_word = await insert_chunk(
        owner_conn, tb["id"], doc_b, content="zanzibar secret word", embedding=FAR
    )
    b_code = await insert_chunk(
        owner_conn,
        tb["id"],
        doc_b,
        chunk_index=1,
        content="code ZZ-9999-Q only here",
        embedding=FAR,
    )
    await owner_conn.commit()

    for query in ("zanzibar", "ZZ-9999-Q", "zanzibar ZZ-9999-Q secret"):
        seen = {hit.chunk_id for hit in await _hits(app_conn, ta, query)}
        assert seen == {a_chunk}, query

    # Positive control: tenant B finds its own chunks through the text branch.
    own = {h.chunk_id: h for h in await _hits(app_conn, tb, "zanzibar ZZ-9999-Q")}
    assert {b_word, b_code} <= set(own)
    assert all("keyword" in own[i].found_by for i in (b_word, b_code))
