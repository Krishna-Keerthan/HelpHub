"""Tenant-scoped semantic search over chunks.

The query is embedded with no transaction open; the search and the titles
lookup then share one short tenant transaction (hnsw.* settings are
transaction-local).
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.repositories.chunks import SearchHit
from app.db.tenant_context import tenant_transaction
from app.services.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

DEFAULT_K = 5
MAX_QUERY_CHARS = 1000


@dataclass(frozen=True)
class SearchResult:
    hits: list[SearchHit]
    # Internal signal (tests, logs); never part of an API response.
    used_fallback: bool


@dataclass(frozen=True)
class TitledHit:
    hit: SearchHit
    document_title: str


async def search_in_session(
    session: AsyncSession, tenant_id: uuid.UUID, embedding: list[float], k: int
) -> SearchResult:
    """ANN top-k, with an exact fallback when ANN misses some of the tenant.

    HNSW is approximate: dead index entries can leave a tenant's nodes
    unreachable (docs/plans/day-03.md). If ANN returns fewer than k hits
    while the tenant has more chunks than that, run the exact search.
    """
    k = chunks_repo.clamp_k(k)
    hits = await chunks_repo.vector_search(session, tenant_id, embedding, k)
    if len(hits) >= k:
        return SearchResult(hits, used_fallback=False)
    available = await chunks_repo.count_for_tenant(session, tenant_id, limit=k)
    if available <= len(hits):
        return SearchResult(hits, used_fallback=False)
    logger.warning(
        "search fallback: tenant=%s ann_hits=%d tenant_chunks_at_least=%d k=%d",
        tenant_id,
        len(hits),
        available,
        k,
    )
    exact = await chunks_repo.exact_search(session, tenant_id, embedding, k)
    return SearchResult(exact, used_fallback=True)


async def search_chunks(
    tenant_id: uuid.UUID, embedding: list[float], k: int
) -> SearchResult:
    async with tenant_transaction(tenant_id) as session:
        return await search_in_session(session, tenant_id, embedding, k)


async def search(
    tenant_id: uuid.UUID, query: str, k: int, provider: EmbeddingProvider
) -> list[TitledHit]:
    embedding = await provider.embed_query(query)  # no transaction open
    async with tenant_transaction(tenant_id) as session:
        result = await search_in_session(session, tenant_id, embedding, k)
        titles = await documents_repo.titles_for(
            session, tenant_id, list({hit.document_id for hit in result.hits})
        )
    return [
        TitledHit(hit, titles[hit.document_id])
        for hit in result.hits
        if hit.document_id in titles
    ]
