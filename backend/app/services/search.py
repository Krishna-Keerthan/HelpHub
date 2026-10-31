"""Tenant-scoped search over chunks: vector and full-text candidates, one query.

The query is embedded with no transaction open; the search and the titles
lookup then share one short tenant transaction (hnsw.* settings are
transaction-local). Chat uses the same function as POST /search.
"""

import logging
import re
import uuid
from dataclasses import dataclass

from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.repositories.chunks import SearchHit, SearchMode, SearchQuery
from app.db.session import DbSession
from app.db.tenant_context import tenant_transaction
from app.services.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

DEFAULT_K = 5
MAX_QUERY_CHARS = 1000
MAX_CODE_TOKENS = 20
MAX_CODE_TOKEN_CHARS = 128
_INNER_DASH = re.compile(r"[A-Za-z0-9]-[A-Za-z0-9]")
_EDGE_PUNCTUATION = ".,;:!?()[]{}\"'"


@dataclass(frozen=True)
class SearchResult:
    hits: list[SearchHit]
    # Internal signal (tests, logs); never part of an API response.
    used_fallback: bool


@dataclass(frozen=True)
class TitledHit:
    hit: SearchHit
    document_title: str


def _is_code_like(token: str) -> bool:
    return (
        any(ch.isdigit() for ch in token)
        or "_" in token
        or bool(_INNER_DASH.search(token))
    )


def split_query(query: str) -> tuple[str, list[str]]:
    """(plain words, identifier-like tokens such as E-4012, ERR_CONN_RESET, v2.3.1)."""
    words: list[str] = []
    codes: list[str] = []
    for raw in query.split():
        token = raw.strip(_EDGE_PUNCTUATION).replace('"', "")
        if token and _is_code_like(token) and len(token) <= MAX_CODE_TOKEN_CHARS:
            if len(codes) < MAX_CODE_TOKENS:
                codes.append(token)
        else:
            words.append(raw)
    return " ".join(words), codes


async def search_in_session(
    session: DbSession,
    tenant_id: uuid.UUID,
    query: str,
    embedding: list[float] | None,
    k: int,
    mode: SearchMode = "hybrid",
) -> SearchResult:
    """Fused top-k, with an exact vector branch when ANN misses some of the tenant.

    HNSW is approximate: dead index entries can leave a tenant's nodes
    unreachable (AR-15). If the ANN branch returns fewer
    candidates than the branch size while the tenant has more chunks than that,
    rerun the statement with the exact vector order.
    """
    words, codes = split_query(query)
    terms = SearchQuery(embedding, words, tuple(codes), k, mode)
    rows = await chunks_repo.search(session, tenant_id, terms)
    wanted = chunks_repo.CANDIDATES
    if mode == "keyword":  # no vector branch, so no ANN completeness to check
        return SearchResult(rows.hits, used_fallback=False)
    if rows.vector_candidates >= wanted:
        return SearchResult(rows.hits, used_fallback=False)
    available = await chunks_repo.count_for_tenant(session, tenant_id, limit=wanted)
    if available <= rows.vector_candidates:
        return SearchResult(rows.hits, used_fallback=False)
    logger.warning(
        "search fallback: tenant=%s ann_candidates=%d tenant_chunks_at_least=%d",
        tenant_id,
        rows.vector_candidates,
        available,
    )
    exact = await chunks_repo.search(session, tenant_id, terms, exact=True)
    return SearchResult(exact.hits, used_fallback=True)


async def search(
    tenant_id: uuid.UUID,
    query: str,
    k: int,
    provider: EmbeddingProvider,
    mode: SearchMode = "hybrid",
) -> list[TitledHit]:
    # Keyword mode never calls the embedding provider.
    embedding = None if mode == "keyword" else await provider.embed_query(query)
    async with tenant_transaction(tenant_id) as session:
        result = await search_in_session(session, tenant_id, query, embedding, k, mode)
        titles = await documents_repo.titles_for(
            session, tenant_id, list({hit.document_id for hit in result.hits})
        )
    return [
        TitledHit(hit, titles[hit.document_id])
        for hit in result.hits
        if hit.document_id in titles
    ]
