"""Fused vector + full-text search: identifiers, rank fusion, query splitting."""

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.tenant_context import set_tenant
from app.services.search import search_in_session, split_query
from tests.conftest import (
    SeededTenant,
    insert_chunk,
    insert_document,
    unit_vector,
)

Q = unit_vector(1.0)
FAR = unit_vector(0.0, 1.0)


@pytest.mark.parametrize(
    ("query", "words", "codes"),
    [
        ("reset my password", "reset my password", []),
        ("What does E-4012 mean?", "What does mean?", ["E-4012"]),
        ("ERR_CONN_RESET, v2.3.1.", "", ["ERR_CONN_RESET", "v2.3.1"]),
        ('say "E-4012" now', "say now", ["E-4012"]),
        ("AB-1234-XL", "", ["AB-1234-XL"]),
    ],
)
def test_split_query_separates_identifiers(
    query: str, words: str, codes: list[str]
) -> None:
    assert split_query(query) == (words, codes)


def test_split_query_caps_identifier_count_and_length() -> None:
    _, codes = split_query(" ".join(f"X-{i}" for i in range(50)))
    assert len(codes) == 20
    assert split_query("A-1" + "x" * 200) == ("A-1" + "x" * 200, [])


async def _search(app_conn: AsyncConnection, tenant: SeededTenant, query: str, k=5):
    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, tenant["id"])
        return await search_in_session(session, tenant["id"], query, Q, k)


async def _seed(owner_conn: AsyncConnection, tenant: SeededTenant, rows):
    doc = await insert_document(owner_conn, tenant["id"], created_by=tenant["user_id"])
    ids = {}
    for i, (content, embedding) in enumerate(rows):
        ids[content] = await insert_chunk(
            owner_conn,
            tenant["id"],
            doc,
            chunk_index=i,
            content=content,
            embedding=embedding,
        )
    await owner_conn.commit()
    return ids


async def test_identifier_is_found_by_text_search_when_vectors_miss(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    ids = await _seed(
        owner_conn,
        ta,
        [
            ("Error E-4012 means the certificate is wrong.", FAR),
            ("Error E-4013 means the clock is off.", FAR),
            ("Nothing relevant here.", unit_vector(1.0, 0.01)),
        ],
    )

    result = await _search(app_conn, ta, "E-4012")

    by_id = {hit.chunk_id: hit for hit in result.hits}
    exact = by_id[ids["Error E-4012 means the certificate is wrong."]]
    assert set(exact.found_by) == {"keyword", "vector"}
    # The near identifier is not matched through the shared fragment.
    other = by_id[ids["Error E-4013 means the clock is off."]]
    assert other.found_by == ("vector",)
    assert result.hits[0].chunk_id == exact.chunk_id  # found by both: ranked first


async def test_chunk_found_by_both_branches_outranks_single_branch_chunks(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    ids = await _seed(
        owner_conn,
        ta,
        [
            ("zebra quasar procedure", unit_vector(1.0, 0.05)),  # both branches
            ("unrelated vector neighbour", unit_vector(1.0, 0.01)),  # vector only
            ("another zebra quasar note", FAR),  # text only
        ],
    )

    result = await _search(app_conn, ta, "zebra quasar")

    assert result.hits[0].chunk_id == ids["zebra quasar procedure"]
    scores = [hit.rrf_score for hit in result.hits]
    assert scores == sorted(scores, reverse=True)
    # score is always the cosine similarity, whichever branch found the chunk.
    text_only = next(
        h for h in result.hits if h.chunk_id == ids["another zebra quasar note"]
    )
    assert text_only.found_by == ("keyword",) or "keyword" in text_only.found_by
    assert -1.0 <= text_only.score <= 1.0


@pytest.mark.parametrize(
    "query",
    ["", "   ", "a & !b | (c", "' ) | & ! <-> :*", '"unbalanced', "E-" * 40],
)
async def test_hostile_or_empty_query_text_never_breaks_the_statement(
    query: str,
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    await _seed(owner_conn, ta, [("some chunk text", unit_vector(1.0, 0.1))])

    result = await _search(app_conn, ta, query)

    assert len(result.hits) == 1  # the vector branch still answers
