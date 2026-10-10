import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

from pgvector.sqlalchemy import Vector
from sqlalchemy import TextClause, bindparam, delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk

# Must match the HNSW index declared in the chunks model and migration 0004.
CHUNKS_EMBEDDING_INDEX = "ix_chunks_embedding_hnsw"
EMBEDDING_DIM = 384
MAX_K = 50
MIN_EF_SEARCH = 40
MAX_EF_SEARCH = 1000

# The ANN scan sits in a MATERIALIZED CTE with an explicit tenant_id filter
# (RLS also applies). The outer query re-sorts by distance: with
# hnsw.iterative_scan = relaxed_order the index may return results slightly out
# of order, and PG17+ needs ORDER BY distance + 0 to keep them re-sortable.
_SEARCH_SQL = """
WITH ann AS MATERIALIZED (
    SELECT id, document_id, text AS content, embedding <=> :vec AS distance
    FROM chunks
    WHERE tenant_id = :tid
    ORDER BY embedding <=> :vec
    LIMIT :k
)
SELECT id AS chunk_id, document_id, content, 1 - distance AS score
FROM ann
ORDER BY distance + 0
LIMIT :k
"""


@dataclass(frozen=True)
class SearchHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    score: float


def clamp_k(k: int) -> int:
    return max(1, min(k, MAX_K))


def vector_search_statement(
    tenant_id: uuid.UUID, embedding: list[float], k: int
) -> TextClause:
    """The one ANN statement, shared by ``vector_search`` and EXPLAIN checks."""
    return text(_SEARCH_SQL).bindparams(
        bindparam("vec", embedding, type_=Vector(EMBEDDING_DIM)),
        bindparam("tid", tenant_id),
        bindparam("k", clamp_k(k)),
    )


def explain_statement(statement: TextClause) -> TextClause:
    """EXPLAIN of ``statement`` with the same bound parameters."""
    return text("EXPLAIN " + statement.text).bindparams(*statement._bindparams.values())


async def vector_search(
    session: AsyncSession, tenant_id: uuid.UUID, embedding: list[float], k: int
) -> list[SearchHit]:
    """Top-``k`` chunks of ``tenant_id`` by cosine similarity.

    Runs in the caller's tenant transaction: set_config(..., true) is lost on
    commit, so tenant setup and search must share one transaction.
    """
    k = clamp_k(k)
    await session.execute(
        text("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)")
    )
    await session.execute(
        text("SELECT set_config('hnsw.ef_search', :ef, true)"),
        {"ef": str(min(max(MIN_EF_SEARCH, k), MAX_EF_SEARCH))},
    )
    rows = await session.execute(vector_search_statement(tenant_id, embedding, k))
    return [SearchHit(*row) for row in rows]


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
