"""POST /search modes: one fused statement, the mode only picks the candidate sets."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import get_embedding_provider
from app.db.repositories.chunks import SearchMode
from app.db.tenant_context import set_tenant
from app.main import app
from app.services.search import search_in_session
from tests.conftest import (
    MakeTenant,
    SeededTenant,
    auth_headers,
    insert_chunk,
    insert_document,
    unit_vector,
)
from tests.helpers.ingestion_helpers import QuerySpyProvider

Q = unit_vector(1.0)
FAR = unit_vector(0.0, 1.0)
WORD = "zanzibar"


async def _seed(owner_conn: AsyncConnection, tenant: SeededTenant) -> dict[str, object]:
    doc = await insert_document(owner_conn, tenant["id"], created_by=tenant["user_id"])
    ids = {
        # near the query vector, no keyword
        "vec_only": await insert_chunk(
            owner_conn,
            tenant["id"],
            doc,
            chunk_index=0,
            content="plain note",
            embedding=Q,
        ),
        # keyword only: far from the query vector
        "kw_far": await insert_chunk(
            owner_conn,
            tenant["id"],
            doc,
            chunk_index=1,
            content=f"{WORD} word",
            embedding=FAR,
        ),
        # both
        "both": await insert_chunk(
            owner_conn,
            tenant["id"],
            doc,
            chunk_index=2,
            content=f"{WORD} again",
            embedding=Q,
        ),
    }
    await owner_conn.commit()
    return ids


async def _hits(
    app_conn: AsyncConnection,
    tenant: SeededTenant,
    mode: SearchMode | None,
    embedding: list[float] | None = Q,
):
    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, tenant["id"])
        if mode is None:
            result = await search_in_session(session, tenant["id"], WORD, embedding, 10)
        else:
            result = await search_in_session(
                session, tenant["id"], WORD, embedding, 10, mode
            )
    return result.hits


async def test_each_mode_returns_its_candidate_sets(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    ids = await _seed(owner_conn, ta)

    hybrid = await _hits(app_conn, ta, "hybrid")
    vector = await _hits(app_conn, ta, "vector")
    keyword = await _hits(app_conn, ta, "keyword", embedding=None)

    assert {h.chunk_id for h in hybrid} == set(ids.values())
    assert {h.chunk_id for h in vector} == set(ids.values())
    assert all(h.found_by == ("vector",) and h.keyword_rank is None for h in vector)
    assert all(h.vector_rank is not None for h in vector)
    assert {h.chunk_id for h in keyword} == {ids["kw_far"], ids["both"]}
    assert all(h.found_by == ("keyword",) and h.vector_rank is None for h in keyword)
    assert all(h.keyword_rank is not None and h.score is None for h in keyword)
    by_id = {h.chunk_id: h for h in hybrid}
    assert by_id[ids["both"]].found_by == ("vector", "keyword")
    assert by_id[ids["both"]].vector_rank and by_id[ids["both"]].keyword_rank
    assert by_id[ids["vec_only"]].keyword_rank is None
    assert by_id[ids["kw_far"]].vector_rank is not None  # vector also lists every chunk


async def test_omitted_mode_is_hybrid(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    await _seed(owner_conn, ta)
    assert await _hits(app_conn, ta, None) == await _hits(app_conn, ta, "hybrid")


async def test_api_keyword_mode_never_calls_the_embedder(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await _seed(owner_conn, tenant)
    spy = QuerySpyProvider()
    app.dependency_overrides[get_embedding_provider] = lambda: spy

    keyword = await client.post(
        "/search", json={"query": WORD, "mode": "keyword"}, headers=auth_headers(tenant)
    )
    assert keyword.status_code == 200
    assert spy.query_calls == 0
    assert {h["found_by"][0] for h in keyword.json()} == {"keyword"}
    assert all(h["score"] is None for h in keyword.json())

    for mode in ("vector", "hybrid"):
        resp = await client.post(
            "/search", json={"query": WORD, "mode": mode}, headers=auth_headers(tenant)
        )
        assert resp.status_code == 200
    assert spy.query_calls == 2


async def test_api_default_mode_matches_hybrid_and_invalid_mode_is_422(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await _seed(owner_conn, tenant)
    headers = auth_headers(tenant)
    default = await client.post("/search", json={"query": WORD}, headers=headers)
    hybrid = await client.post(
        "/search", json={"query": WORD, "mode": "hybrid"}, headers=headers
    )
    assert default.status_code == hybrid.status_code == 200
    assert default.json() == hybrid.json()
    for bad in ("fuzzy", "", "HYBRID", None):
        resp = await client.post(
            "/search", json={"query": WORD, "mode": bad}, headers=headers
        )
        assert resp.status_code == 422
