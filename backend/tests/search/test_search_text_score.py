"""text_score is internal and additive: the same chunks in the same order, in every mode."""

import re

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.repositories import chunks as chunks_repo
from app.db.repositories.chunks import SearchMode, SearchQuery
from app.db.tenant_context import set_tenant
from tests.conftest import SeededTenant, insert_chunk, insert_document, unit_vector

Q = unit_vector(1.0)
FAR = unit_vector(0.0, 1.0)
WORD = "zanzibar"


def _without_text_score(sql: str) -> str:
    """The statement as it was before text_score: strip exactly what was added."""
    sql = sql.replace(
        ",\n           ts_rank_cd(c.search_tsv, q.tsq, 32) AS text_score", ""
    )
    sql = sql.replace(", kw.text_score", "").replace(
        "LEFT JOIN kw ON kw.id = f.id\n", ""
    )
    assert "text_score" not in sql and "LEFT JOIN kw" not in sql
    return sql


async def _seed(owner_conn: AsyncConnection, tenant: SeededTenant) -> None:
    doc = await insert_document(owner_conn, tenant["id"], created_by=tenant["user_id"])
    rows = [
        ("plain note", Q),
        (f"{WORD} word", FAR),
        (f"{WORD} {WORD} again and again", Q),
        (f"{WORD} in a much longer sentence about nothing in particular at all", Q),
    ]
    for i, (content, embedding) in enumerate(rows):
        await insert_chunk(
            owner_conn,
            tenant["id"],
            doc,
            chunk_index=i,
            content=content,
            embedding=embedding,
        )
    await owner_conn.commit()


async def _rows(
    session: AsyncSession, tenant: SeededTenant, query: SearchQuery, legacy: bool
):
    statement = chunks_repo.search_statement(tenant["id"], query)
    if legacy:
        statement = text(_without_text_score(str(statement))).bindparams(
            *statement._bindparams.values()
        )
    return list(await session.execute(statement))


@pytest.mark.parametrize("mode", ["hybrid", "vector", "keyword"])
async def test_results_identical_with_and_without_the_column(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    make_tenant,
    mode: SearchMode,
) -> None:
    tenant = await make_tenant()
    await _seed(owner_conn, tenant)
    query = SearchQuery(embedding=Q, words=WORD, codes=(), k=10, mode=mode)
    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, tenant["id"])
        new = await _rows(session, tenant, query, legacy=False)
        old = await _rows(session, tenant, query, legacy=True)
    assert new and [tuple(r[:12]) for r in new] == [tuple(r[:12]) for r in old]
    assert all(len(r) == 13 for r in new) and all(len(r) == 12 for r in old)


@pytest.mark.parametrize("mode", ["hybrid", "vector", "keyword"])
async def test_text_score_is_null_exactly_outside_the_keyword_branch(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    make_tenant,
    mode: SearchMode,
) -> None:
    tenant = await make_tenant()
    await _seed(owner_conn, tenant)
    query = SearchQuery(embedding=Q, words=WORD, codes=(), k=10, mode=mode)
    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, tenant["id"])
        hits = (await chunks_repo.search(session, tenant["id"], query)).hits
    assert hits
    for hit in hits:
        if hit.keyword_rank is None:
            assert hit.text_score is None
        else:
            assert hit.text_score is not None and 0 < hit.text_score < 1
    in_keyword = [h for h in hits if h.keyword_rank is not None]
    # normalised score keeps the keyword order (it is monotonic in the raw rank)
    ordered = sorted(in_keyword, key=lambda h: h.keyword_rank)
    assert [h.text_score for h in ordered] == sorted(
        (h.text_score for h in in_keyword), reverse=True
    )


def test_normalisation_flag_is_32() -> None:
    assert re.search(
        r"ts_rank_cd\(c\.search_tsv, q\.tsq, 32\) AS text_score",
        chunks_repo._SEARCH_SQL,
    )
