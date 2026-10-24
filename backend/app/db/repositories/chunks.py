import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, TypedDict

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    TextClause,
    bindparam,
    delete,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk

# Must match the HNSW index declared in the chunks model and migration 0004.
CHUNKS_EMBEDDING_INDEX = "ix_chunks_embedding_hnsw"
EMBEDDING_DIM = 384
MAX_K = 50
SearchMode = Literal["hybrid", "vector", "keyword"]
MIN_EF_SEARCH = 40
MAX_EF_SEARCH = 1000

# Ties are broken by document title, then chunk position (never by random ids).
# One statement, two candidate sets, fused by reciprocal rank in SQL. Both
# branches filter by the same TENANT_FILTER (RLS also applies), and so does the
# final join. The vector branch is a MATERIALIZED CTE: with
# hnsw.iterative_scan = relaxed_order the index may return results slightly out
# of order, so ranks are taken from ``distance + 0`` (PG17+ needs that to keep
# them re-sortable). Only ranks enter the fusion, never raw scores (AR-11).
TSCONFIG = "english"  # must match the generated column (migration 0009)
TENANT_FILTER = "tenant_id = :tid"
CANDIDATES = 50  # per branch
RRF_K = 60

_SEARCH_SQL = """
WITH q AS MATERIALIZED (SELECT {tsquery} AS tsq),
vec AS MATERIALIZED (
    SELECT id, document_id, chunk_index, embedding <=> :vec AS distance
    FROM chunks
    WHERE {tenant}
    ORDER BY {order_by}
    LIMIT :vec_cand
),
kw AS MATERIALIZED (
    SELECT c.id, c.document_id, c.chunk_index, ts_rank_cd(c.search_tsv, q.tsq) AS rank_value,
           ts_rank_cd(c.search_tsv, q.tsq, 32) AS text_score
    FROM chunks c
    JOIN documents d ON d.id = c.document_id AND d.tenant_id = :tid, q
    WHERE c.{tenant} AND c.search_tsv @@ q.tsq
    ORDER BY rank_value DESC, d.title, c.chunk_index, c.id
    LIMIT :kw_cand
),
ranked AS (
    SELECT v.id, d.title, v.chunk_index, 'vector' AS source,
           row_number() OVER (ORDER BY v.distance + 0, d.title, v.chunk_index, v.id) AS pos
    FROM vec v JOIN documents d ON d.id = v.document_id AND d.tenant_id = :tid
    UNION ALL
    SELECT k.id, d.title, k.chunk_index, 'keyword' AS source,
           row_number() OVER (ORDER BY k.rank_value DESC, d.title, k.chunk_index, k.id) AS pos
    FROM kw k JOIN documents d ON d.id = k.document_id AND d.tenant_id = :tid
),
fused AS (
    SELECT id, min(title) AS title, min(chunk_index) AS chunk_index,
           sum(1.0 / (:rrf_k + pos))::float8 AS rrf_score, min(pos) AS best_pos,
           array_agg(source ORDER BY source DESC) AS found_by,
           max(pos) FILTER (WHERE source = 'vector') AS vector_rank,
           max(pos) FILTER (WHERE source = 'keyword') AS keyword_rank
    FROM ranked
    GROUP BY id
    ORDER BY rrf_score DESC, best_pos, min(title), min(chunk_index), id
    LIMIT :k
)
SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.text AS content,
       c.char_start, c.char_end, 1 - (c.embedding <=> :vec) AS score,
       f.rrf_score, f.found_by, (SELECT count(*) FROM vec) AS vector_candidates,
       f.vector_rank, f.keyword_rank, kw.text_score
FROM fused f
JOIN chunks c ON c.id = f.id AND c.{tenant}
LEFT JOIN kw ON kw.id = f.id
ORDER BY f.rrf_score DESC, f.best_pos, f.title, f.chunk_index, c.id
"""
# ANN: the HNSW index can supply this order.
_ANN_ORDER = "embedding <=> :vec"
# Exact: "+ 0" makes the expression unusable by the HNSW index, so the plan
# must compute every distance of the tenant's rows (found via
# ix_chunks_tenant_id) and sort them. No planner flags needed.
_EXACT_ORDER = "(embedding <=> :vec) + 0"


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    score: (
        float | None
    )  # cosine to the query, whichever branch found it; None in keyword mode
    rrf_score: float  # orders the results
    found_by: tuple[str, ...]  # "vector", "keyword" or both
    vector_rank: int | None = None  # 1-based position in the vector candidates
    keyword_rank: int | None = None  # 1-based position in the keyword candidates
    # ts_rank_cd normalised by rank/(rank+1) (flag 32), in [0, 1); None when the
    # chunk was not in the keyword branch. Internal: never ordered by, never in the API.
    text_score: float | None = None


@dataclass(frozen=True)
class SearchRows:
    hits: list[SearchHit]
    vector_candidates: int  # size of the vector branch (ANN completeness check)


def clamp_k(k: int) -> int:
    return max(1, min(k, MAX_K))


def _tsquery_sql(code_count: int) -> str:
    """OR of the plain words and of each identifier as an exact phrase.

    plainto_tsquery ANDs its terms; the words are turned into an OR so one
    unmatched word does not hide a chunk. An identifier such as E-4012 parses to
    adjacent tokens, and the quoted websearch form matches them as a phrase, so
    it does not match E-4013 through a shared fragment.
    """
    parts = [
        f"replace(plainto_tsquery('{TSCONFIG}', :words)::text, ' & ', ' | ')::tsquery"
    ]
    parts += [
        f"websearch_to_tsquery('{TSCONFIG}', :code{i})" for i in range(code_count)
    ]
    return " || ".join(parts)


@dataclass(frozen=True)
class SearchQuery:
    embedding: list[float] | None  # None only for mode "keyword"
    words: str  # plain words, OR'd in the full-text branch
    codes: tuple[str, ...]  # identifiers, each matched as an exact phrase
    k: int
    # Which candidate sets feed the fused query: a branch not wanted gets
    # LIMIT 0, so the statement (and its tenant filters) stays the same.
    mode: SearchMode = "hybrid"


def search_statement(
    tenant_id: uuid.UUID, query: SearchQuery, *, exact: bool = False
) -> TextClause:
    """The one search statement, shared by ``search`` and EXPLAIN checks.

    ``exact`` replaces the ANN order by a full computation over the tenant's
    rows; it is the fallback when ANN misses some of them.
    """
    params = [
        bindparam("vec", query.embedding, type_=Vector(EMBEDDING_DIM)),
        bindparam("tid", tenant_id),
        bindparam("k", clamp_k(query.k)),
        bindparam("vec_cand", 0 if query.mode == "keyword" else CANDIDATES),
        bindparam("kw_cand", 0 if query.mode == "vector" else CANDIDATES),
        bindparam("rrf_k", RRF_K),
        bindparam("words", query.words),
    ]
    params += [bindparam(f"code{i}", f'"{c}"') for i, c in enumerate(query.codes)]
    return text(
        _SEARCH_SQL.format(
            tsquery=_tsquery_sql(len(query.codes)),
            tenant=TENANT_FILTER,
            order_by=_EXACT_ORDER if exact else _ANN_ORDER,
        )
    ).bindparams(*params)


async def search(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query: SearchQuery,
    *,
    exact: bool = False,
) -> SearchRows:
    """Top-``k`` chunks of ``tenant_id`` by fused vector and full-text rank.

    Runs in the caller's tenant transaction: set_config(..., true) is lost on
    commit, so tenant setup and search must share one transaction.
    """
    if not exact:
        await session.execute(
            text("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)")
        )
        await session.execute(
            text("SELECT set_config('hnsw.ef_search', :ef, true)"),
            {"ef": str(min(max(MIN_EF_SEARCH, CANDIDATES), MAX_EF_SEARCH))},
        )
    rows = list(await session.execute(search_statement(tenant_id, query, exact=exact)))
    hits = [SearchHit(*row[:8], tuple(row[8]), *row[10:13]) for row in rows]
    return SearchRows(hits, rows[0][9] if rows else 0)


async def count_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, *, limit: int
) -> int:
    """Chunks of ``tenant_id``, counted up to ``limit`` (an index lookup)."""
    capped = (
        select(Chunk.id).where(Chunk.tenant_id == tenant_id).limit(limit).subquery()
    )
    result = await session.execute(select(func.count()).select_from(capped))
    return result.scalar_one()


class NewChunk(TypedDict):
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    embedding: list[float]


async def delete_for_document(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> int:
    result = await session.execute(
        delete(Chunk).where(
            Chunk.tenant_id == tenant_id, Chunk.document_id == document_id
        )
    )
    return result.rowcount


async def insert_many(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    chunks: Sequence[NewChunk],
    *,
    embedding_model: str,
) -> None:
    """Bulk insert ``chunks`` for one document (a single executemany)."""
    if not chunks:
        return
    await session.execute(
        insert(Chunk),
        [
            {
                **chunk,
                "tenant_id": tenant_id,
                "document_id": document_id,
                "embedding_model": embedding_model,
            }
            for chunk in chunks
        ],
    )


async def count_for_document(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.tenant_id == tenant_id, Chunk.document_id == document_id)
    )
    return result.scalar_one()
