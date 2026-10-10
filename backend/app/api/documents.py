from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentPrincipal, Embedder
from app.schemas.document import DocumentCreate, DocumentRead
from app.services import documents as documents_service

router = APIRouter(prefix="/documents", tags=["documents"])


# CurrentPrincipal, never CurrentUser/TenantSession: those keep a transaction
# open for the whole request, and this route embeds (slow) inline.
@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": DocumentRead}},
)
async def create_document(
    data: DocumentCreate,
    principal: CurrentPrincipal,
    provider: Embedder,
    response: Response,
) -> DocumentRead:
    try:
        document, created = await documents_service.create_or_get(
            principal.tenant_id, principal.user_id, data.title, data.content
        )
        if document.status != documents_service.READY:
            document = await documents_service.ingest_document(
                principal.tenant_id, document.id, provider
            )
    except documents_service.EmptyDocument:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Document is empty"
        ) from None
    except documents_service.DocumentTooLarge:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, detail="Document is too large"
        ) from None
    except documents_service.IngestionError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document ingestion failed"
        ) from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return DocumentRead.model_validate(document)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    principal: CurrentPrincipal,
    limit: Annotated[
        int, Query(ge=1, le=documents_service.MAX_LIMIT)
    ] = documents_service.DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentRead]:
    documents = await documents_service.list_documents(
        principal.tenant_id, limit=limit, offset=offset
    )
    return [DocumentRead.model_validate(d) for d in documents]
