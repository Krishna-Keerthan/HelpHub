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


async def test_chunk_found_by_both_branches_outranks_a_vector_only_neighbour(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    ids = await _seed(
        owner_conn,
        ta,
        [
            ("zebra quasar procedure", unit_vector(1.0, 0.05)),  # vector rank 2 + text
            ("unrelated vector neighbour", unit_vector(1.0, 0.01)),  # vector rank 1
            ("nothing to see", FAR),  # vector rank 3, no text match
        ],
    )

    result = await _search(app_conn, ta, "zebra quasar")

    assert [hit.chunk_id for hit in result.hits] == [
        ids["zebra quasar procedure"],
        ids["unrelated vector neighbour"],
        ids["nothing to see"],
    ]
    both, neighbour, last = result.hits
    assert set(both.found_by) == {"vector", "keyword"}
    assert neighbour.found_by == last.found_by == ("vector",)
    assert both.rrf_score > neighbour.rrf_score > last.rrf_score
    # score stays the cosine similarity, whichever branch found the chunk.
    assert neighbour.score > both.score > last.score


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
