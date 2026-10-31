import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.chunks import (
    CHUNKS_EMBEDDING_INDEX,
    SearchQuery,
    search,
    search_statement,
)
from app.db.tenant_context import set_tenant
from tests.conftest import (
    auth_headers,
    insert_chunk,
    insert_chunks,
    insert_document,
    unit_vector,
)
from tests.helpers.plans import explain_statement
from tests.isolation.ann_helpers import ensure_ann_reachable

SHARED_TEXT = (
    "To reset your password, open the account settings page and choose the "
    "security tab.\n\n"
    "Then click the reset link and follow the instructions sent to your email "
    "address. The link expires after one hour, so request a new one if needed."
)


async def _chunk_ids_by_tenant(owner_conn, tenant_id) -> set[str]:
    result = await owner_conn.execute(
        text("SELECT id FROM chunks WHERE tenant_id = :tid"), {"tid": tenant_id}
    )
    return {str(row[0]) for row in result}


@pytest.mark.asyncio
async def test_same_text_searched_isolates_tenants(
    client, owner_conn, two_tenants_seeded
):
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]
    payload = {"title": "Reset password", "content": SHARED_TEXT}

    # Upload same text payload for both tenants.
    for tenant in (ta, tb):
        created = await client.post(
            "/documents", json=payload, headers=auth_headers(tenant)
        )
        assert created.status_code == 201

    a_chunks = await _chunk_ids_by_tenant(owner_conn, ta["id"])
    b_chunks = await _chunk_ids_by_tenant(owner_conn, tb["id"])
    assert a_chunks and b_chunks
    assert a_chunks.isdisjoint(b_chunks)

    # Search as A with the very same text: only A chunk IDs come back.
    response = await client.post(
        "/search",
        json={"query": SHARED_TEXT, "k": 10},
        headers=auth_headers(ta),
    )
    assert response.status_code == 200
    hits = response.json()
    returned = {hit["chunk_id"] for hit in hits}
    assert returned
    assert returned <= a_chunks
    assert returned.isdisjoint(b_chunks)
    scores = [hit["score"] for hit in hits]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_filtered_ann_with_hnsw(owner_conn, app_conn, two_tenants_seeded):
    """
    Tenant B gets 200 chunks very close to query q. Tenant A gets 3 chunks far from q.
    With enable_seqscan = off, search as A with k=3 must return A's 3 chunks.
    """
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]
    q = unit_vector(1.0)
    # There is deliberately no tenant_id btree on chunks, so the planner has no
    # competing index path. See AR-15 in docs/review/accepted-risks.md for the
    # trade-off and the fallback if one is re-added.

    # Seed as owner: 200 chunks of B right next to q, 3 chunks of A far from q.
    doc_a = await insert_document(owner_conn, ta["id"], created_by=ta["user_id"])
    doc_b = await insert_document(owner_conn, tb["id"], created_by=tb["user_id"])
    await insert_chunks(
        owner_conn,
        tb["id"],
        doc_b,
        [unit_vector(1.0, 0.001 * (i + 1)) for i in range(200)],
    )
    a_ids = {
        str(
            await insert_chunk(
                owner_conn,
                ta["id"],
                doc_a,
                chunk_index=i,
                embedding=unit_vector(0.0, 1.0, 0.1 * (i + 1)),
            )
        )
        for i in range(3)
    }
    await owner_conn.commit()
    await ensure_ann_reachable(owner_conn, [uuid.UUID(i) for i in a_ids], q)

    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, ta["id"])
        await app_conn.execute(text("SET LOCAL enable_seqscan = off"))
        hits = (await search(session, ta["id"], SearchQuery(q, "", (), 3))).hits
        # The plan of the very statement the service runs must use the HNSW
        # index, otherwise this test would pass by accident through a seq scan.
        plan = await session.execute(
            explain_statement(search_statement(ta["id"], SearchQuery(q, "", (), 3)))
        )
        plan_text = "\n".join(row[0] for row in plan)

    assert len(hits) == 3
    assert {str(hit.chunk_id) for hit in hits} == a_ids
    assert CHUNKS_EMBEDDING_INDEX in plan_text, plan_text


@pytest.mark.asyncio
async def test_search_raw_sql_no_tenant_context(
    owner_conn, app_conn, two_tenants_seeded
):
    ta = two_tenants_seeded["tenant_a"]
    doc_a = await insert_document(owner_conn, ta["id"], created_by=ta["user_id"])
    await insert_chunk(owner_conn, ta["id"], doc_a)
    await owner_conn.commit()

    # Without tenant context the runtime role sees nothing, though a row exists.
    result = await app_conn.execute(text("SELECT count(*) FROM chunks"))
    assert result.scalar_one() == 0

    # Positive control: with the tenant set, the same row is visible.
    await app_conn.execute(
        text("SELECT set_config('app.tenant_id', :tid, false)"),
        {"tid": str(ta["id"])},
    )
    result = await app_conn.execute(text("SELECT count(*) FROM chunks"))
    assert result.scalar_one() == 1


def test_search_statement_is_tenant_filtered_and_materialized():
    tid = uuid.uuid4()
    statement = search_statement(tid, SearchQuery(unit_vector(1.0), "", (), 3))
    assert "AS MATERIALIZED" in statement.text
    assert "WHERE tenant_id = :tid" in statement.text
    assert statement.compile().params["tid"] == tid
    assert statement.compile().params["k"] == 3
