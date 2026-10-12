from typing import Annotated

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentPrincipal, Embedder
from app.schemas.search import KeywordSearchRequest, SearchHitRead, SearchRequest
from app.services import keyword_search
from app.services import search as search_service
from app.services.es_client import get_es

router = APIRouter(prefix="/search", tags=["search"])


def _read(results: list[search_service.TitledHit]) -> list[SearchHitRead]:
    return [
        SearchHitRead(
            chunk_id=r.hit.chunk_id,
            document_id=r.hit.document_id,
            document_title=r.document_title,
            chunk_index=r.hit.chunk_index,
            content=r.hit.content,
            char_start=r.hit.char_start,
            char_end=r.hit.char_end,
            score=r.hit.score,
        )
        for r in results
    ]


# CurrentPrincipal, never CurrentUser/TenantSession: the query is embedded
# before any transaction opens.
@router.post("", response_model=list[SearchHitRead])
async def search(
    data: SearchRequest, principal: CurrentPrincipal, provider: Embedder
) -> list[SearchHitRead]:
    results = await search_service.search(
        principal.tenant_id, data.query, data.k, provider
    )
    return _read(results)


# Same reasoning: Elasticsearch is called with no transaction open.
# ``score`` is the raw BM25 score: unbounded and relative to the corpus, so it
# is NOT comparable to the cosine score of POST /search.
@router.post("/keyword", response_model=list[SearchHitRead])
async def keyword(
    data: KeywordSearchRequest,
    principal: CurrentPrincipal,
    es: Annotated[AsyncElasticsearch, Depends(get_es)],
) -> list[SearchHitRead]:
    try:
        results = await keyword_search.search(
            principal.tenant_id, data.query, data.k, es
        )
    except keyword_search.SearchUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="search unavailable"
        ) from None
    return _read(results)
