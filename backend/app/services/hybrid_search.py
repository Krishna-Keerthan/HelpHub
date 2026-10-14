"""Hybrid search: BM25 (Elasticsearch) and vector (pgvector) fused with RRF.

The branches are independent. Each has its own budget and its own short tenant
transaction; no transaction is open while the query is embedded or while
Elasticsearch is called. A branch that fails or times out is dropped and
reported in ``degraded``; only when both fail is the search unavailable. Only
ranks enter the fusion, never the raw scores (AR-11).
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from elasticsearch import AsyncElasticsearch

from app.core.config import settings
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.tenant_context import tenant_transaction
from app.services import keyword_search
from app.services.embeddings import EmbeddingProvider
from app.services.rrf import fuse_rrf
from app.services.search import TitledHit, search_in_session

logger = logging.getLogger(__name__)

Branch = Literal["vector", "keyword"]


class HybridUnavailable(Exception):
    """Both branches failed. Carries no backend text."""


@dataclass(frozen=True)
class HybridHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    content: str
    char_start: int
    char_end: int
    rrf_score: float
    found_by: list[Branch]
    vector_score: float | None
    keyword_score: float | None


@dataclass(frozen=True)
class HybridResult:
    hits: list[HybridHit]
    degraded: list[Branch]
    # Internal signal (logs, tests); never part of an API response.
    vector_fallback: bool


async def _vector_branch(
    tenant_id: uuid.UUID, query: str, candidates: int, provider: EmbeddingProvider
) -> tuple[list[TitledHit], bool]:
    embedding = await provider.embed_query(query)  # no transaction open
    async with tenant_transaction(tenant_id) as session:
        result = await search_in_session(session, tenant_id, embedding, candidates)
        titles = await documents_repo.titles_for(
            session, tenant_id, list({hit.document_id for hit in result.hits})
        )
    hits = [
        TitledHit(hit, titles[hit.document_id])
        for hit in result.hits
        if hit.document_id in titles
    ]
    return hits, result.used_fallback


async def _keyword_branch(
    tenant_id: uuid.UUID, query: str, candidates: int, es: AsyncElasticsearch
) -> list[TitledHit]:
    return await keyword_search.search(tenant_id, query, candidates, es)


def _failed(branch: Branch, error: BaseException) -> None:
    # Class name only: backend messages can echo queries or document text.
    logger.warning(
        "hybrid branch failed: branch=%s error=%s", branch, type(error).__name__
    )


async def hybrid_search(
    tenant_id: uuid.UUID,
    query: str,
    k: int,
    provider: EmbeddingProvider,
    es: AsyncElasticsearch,
) -> HybridResult:
    k = max(1, min(k, chunks_repo.MAX_K))
    candidates = max(k, min(settings.hybrid_candidates, chunks_repo.MAX_K))
    budget = settings.hybrid_branch_timeout_seconds

    vector, keyword = await asyncio.gather(
        asyncio.wait_for(
            _vector_branch(tenant_id, query, candidates, provider), budget
        ),
        asyncio.wait_for(_keyword_branch(tenant_id, query, candidates, es), budget),
        return_exceptions=True,
    )
    for outcome in (vector, keyword):
        if isinstance(outcome, asyncio.CancelledError):
            raise outcome  # the request itself was cancelled

    degraded: list[Branch] = []
    ranked: list[list[uuid.UUID]] = []
    by_branch: dict[Branch, dict[uuid.UUID, TitledHit]] = {}
    fallback = False

    if isinstance(vector, BaseException):
        _failed("vector", vector)
        degraded.append("vector")
    else:
        vector_hits, fallback = vector
        by_branch["vector"] = {h.hit.chunk_id: h for h in vector_hits}
        ranked.append([h.hit.chunk_id for h in vector_hits])
    if isinstance(keyword, BaseException):
        _failed("keyword", keyword)
        degraded.append("keyword")
    else:
        by_branch["keyword"] = {h.hit.chunk_id: h for h in keyword}
        ranked.append([h.hit.chunk_id for h in keyword])

    if not by_branch:
        raise HybridUnavailable("search unavailable")
    if fallback:
        logger.info("hybrid vector_fallback=1 tenant=%s", tenant_id)

    hits: list[HybridHit] = []
    for chunk_id, score in fuse_rrf(ranked, k=settings.rrf_k)[:k]:
        found_by: list[Branch] = []
        if chunk_id in by_branch.get("vector", {}):
            found_by.append("vector")
        if chunk_id in by_branch.get("keyword", {}):
            found_by.append("keyword")
        titled = by_branch[found_by[0]][chunk_id]
        hits.append(
            HybridHit(
                chunk_id=chunk_id,
                document_id=titled.hit.document_id,
                document_title=titled.document_title,
                chunk_index=titled.hit.chunk_index,
                content=titled.hit.content,
                char_start=titled.hit.char_start,
                char_end=titled.hit.char_end,
                rrf_score=score,
                found_by=found_by,
                vector_score=(
                    by_branch["vector"][chunk_id].hit.score
                    if "vector" in found_by
                    else None
                ),
                keyword_score=(
                    by_branch["keyword"][chunk_id].hit.score
                    if "keyword" in found_by
                    else None
                ),
            )
        )
    return HybridResult(hits, degraded, fallback)
