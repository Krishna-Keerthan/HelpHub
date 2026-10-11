import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.deps import AdminUser, CurrentPrincipal, Embedder, Principal
from app.api.uploads import (
    MULTIPART_OVERHEAD,
    media_type,
    parse_multipart,
    read_bounded,
)
from app.core.config import settings
from app.schemas.document import ChunkRead, DocumentCreate, DocumentRead
from app.services import documents as documents_service
from app.services import extraction
from app.services.embeddings import EmbeddingProvider

router = APIRouter(prefix="/documents", tags=["documents"])

# A JSON body holds at most max_document_chars characters (<= 4 UTF-8 bytes
# each, plus JSON escaping headroom).
JSON_BODY_OVERHEAD = 64 * 1024

_DOCUMENT_CREATE_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": DocumentCreate.model_json_schema()}},
    }
}
_UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "title": {"type": "string", "maxLength": 500},
                    },
                }
            }
        },
    }
}


def _unsupported_media_type(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")


async def _create_and_ingest(
    principal: Principal,
    title: str,
    content: str,
    provider: EmbeddingProvider,
    response: Response,
) -> DocumentRead:
    """Shared by the JSON and upload routes; maps service errors to HTTP."""
    try:
        document, created = await documents_service.create_or_get(
            principal.tenant_id, principal.user_id, title, content
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
    except documents_service.DocumentNotFound:
        # The row vanished mid-flight (e.g. deleted concurrently).
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Document changed while it was being processed; retry",
        ) from None
    except documents_service.IngestionError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document ingestion failed"
        ) from None
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return DocumentRead.model_validate(document)


# CurrentPrincipal, never CurrentUser/TenantSession: those keep a transaction
# open for the whole request, and these routes embed (slow) inline.
# The body is parsed explicitly so that anything but application/json is a
# 415 (FastAPI would otherwise try to parse a missing Content-Type as JSON).
@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": DocumentRead}, 415: {}},
    openapi_extra=_DOCUMENT_CREATE_BODY,
)
async def create_document(
    request: Request,
    principal: CurrentPrincipal,
    provider: Embedder,
    response: Response,
) -> DocumentRead:
    if media_type(request) != "application/json":
        raise _unsupported_media_type("Use application/json, or POST /documents/upload")
    body = await read_bounded(
        request, settings.max_document_chars * 4 + JSON_BODY_OVERHEAD
    )
    try:
        data = DocumentCreate.model_validate_json(body)
    except ValidationError as exc:
        errors = exc.errors(
            include_url=False, include_context=False, include_input=False
        )
        raise RequestValidationError(
            [{**error, "loc": ("body", *error["loc"])} for error in errors]
        ) from None
    return await _create_and_ingest(
        principal, data.title, data.content, provider, response
    )


@router.post(
    "/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": DocumentRead}, 413: {}, 415: {}},
    openapi_extra=_UPLOAD_BODY,
)
async def upload_document(
    request: Request,
    principal: CurrentPrincipal,
    provider: Embedder,
    response: Response,
) -> DocumentRead:
    if media_type(request) != "multipart/form-data":
        raise _unsupported_media_type("Use multipart/form-data with a 'file' field")
    body = await read_bounded(request, settings.max_upload_bytes + MULTIPART_OVERHEAD)
    form = parse_multipart(request.headers["content-type"], body)
    upload = form.files.get("file")
    if upload is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Missing 'file' field"
        )
    if len(upload.data) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, detail="File is too large"
        )
    try:
        extraction.check_extension(upload.filename)
        content = await extraction.extract_text(upload.filename, upload.data)
    except extraction.UnsupportedFileType as exc:
        raise _unsupported_media_type(str(exc)) from None
    except extraction.ExtractedTextTooLarge:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, detail="Document is too large"
        ) from None
    except extraction.PdfQueueTimeout:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server busy, retry shortly",
            headers={"Retry-After": str(int(settings.pdf_queue_wait_seconds) or 1)},
        ) from None
    except extraction.UnreadableDocument as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from None

    title = (form.fields.get("title") or "").strip() or extraction.base_name(
        upload.filename
    )
    if not title or len(title) > extraction.MAX_TITLE_CHARS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid title"
        )
    return await _create_and_ingest(principal, title, content, provider, response)


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


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID, principal: CurrentPrincipal
) -> DocumentRead:
    try:
        document = await documents_service.get_document(
            principal.tenant_id, document_id
        )
    except documents_service.DocumentNotFound:
        raise _not_found() from None
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/chunks", response_model=list[ChunkRead])
async def list_chunks(
    document_id: uuid.UUID,
    principal: CurrentPrincipal,
    limit: Annotated[
        int, Query(ge=1, le=documents_service.MAX_LIMIT)
    ] = documents_service.DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ChunkRead]:
    try:
        chunks = await documents_service.list_chunks(
            principal.tenant_id, document_id, limit=limit, offset=offset
        )
    except documents_service.DocumentNotFound:
        raise _not_found() from None
    return [ChunkRead.model_validate(chunk) for chunk in chunks]


@router.delete(
    "/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_document(document_id: uuid.UUID, admin: AdminUser) -> None:
    try:
        await documents_service.delete_document(admin.tenant_id, document_id)
    except documents_service.DocumentNotFound:
        raise _not_found() from None
