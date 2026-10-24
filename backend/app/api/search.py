from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentPrincipal, Embedder
from app.api.rate_limit import SearchLimit
from app.schemas.search import SearchHitRead, SearchRequest
from app.services import search as search_service
from app.services.embeddings import EmbeddingUnavailableError

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
            rrf_score=r.hit.rrf_score,
            found_by=list(r.hit.found_by),  # type: ignore[arg-type]
            vector_rank=r.hit.vector_rank,
            keyword_rank=r.hit.keyword_rank,
        )
        for r in results
    ]


# CurrentPrincipal, never CurrentUser/TenantSession: the query is embedded
# before any transaction opens.
@router.post("", response_model=list[SearchHitRead], dependencies=[SearchLimit])
async def search(
    data: SearchRequest, principal: CurrentPrincipal, provider: Embedder
) -> list[SearchHitRead]:
    try:
        results = await search_service.search(
            principal.tenant_id, data.query, data.k, provider, data.mode
        )
    except EmbeddingUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Embedding service unavailable"
        ) from None
    return _read(results)
