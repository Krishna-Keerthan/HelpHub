"""Document creation and ingestion (chunk, embed, store).

Worker-ready: every function takes ``tenant_id`` explicitly and opens its own
short ``tenant_transaction``; the embedding provider is always a parameter.
Embedding runs with no transaction open, so a slow model never holds a
database connection or row locks.
"""

import hashlib
import logging
import uuid

from app.core.config import settings
from app.db.models import Document
from app.db.models.chunk import EMBEDDING_DIM
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.tenant_context import tenant_transaction
from app.services.chunker import chunk_text
from app.services.embeddings import EmbeddingError, EmbeddingProvider, validate_vectors

logger = logging.getLogger(__name__)

PENDING = "PENDING"
READY = "READY"
FAILED = "FAILED"
ERROR_MAX_CHARS = 500
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


class DocumentError(Exception):
    """Base for our own errors; their messages never contain document content."""


class EmptyDocument(DocumentError):
    pass


class DocumentTooLarge(DocumentError):
    pass


class DocumentNotFound(DocumentError):
    pass


class IngestionError(DocumentError):
    pass


# Only these messages are safe to store; anything else is stored as its class
# name alone (a driver error can echo SQL or row values).
_SAFE_MESSAGE_ERRORS = (DocumentError, EmbeddingError)


def prepare_text(content: str) -> str:
    """Strip NUL bytes only (Postgres text cannot hold them) and validate.

    Nothing else is normalised: chunk offsets index into the stored text.
    """
    text = content.replace("\x00", "")
    if not text.strip():
        raise EmptyDocument("document is empty")
    if len(text) > settings.max_document_chars:
        raise DocumentTooLarge(
            f"document exceeds {settings.max_document_chars} characters"
        )
    return text


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def error_summary(exc: BaseException) -> str:
    name = type(exc).__name__
    if isinstance(exc, _SAFE_MESSAGE_ERRORS) and str(exc):
        return f"{name}: {exc}"[:ERROR_MAX_CHARS]
    return name[:ERROR_MAX_CHARS]


async def create_or_get(
    tenant_id: uuid.UUID, user_id: uuid.UUID, title: str, content: str
) -> tuple[Document, bool]:
    """Return ``(document, created)`` for this content in this tenant.

    Race-safe through INSERT ... ON CONFLICT ON CONSTRAINT
    uq_documents_tenant_id_content_hash DO NOTHING: a concurrent loser waits
    for the winner's commit, inserts nothing, and the follow-up SELECT (a new
    READ COMMITTED snapshot) sees the winner's row. No savepoint, and the
    transaction never enters an aborted state. A FAILED document is reset to
    PENDING so the caller can retry ingestion on the same row.
    """
    raw_text = prepare_text(content)
    digest = content_hash(raw_text)
    # Second attempt only if the conflicting row vanished in between (deleted
    # after it blocked our insert); then our insert can succeed.
    for _ in range(2):
        async with tenant_transaction(tenant_id) as session:
            created = await documents_repo.insert_if_absent(
                session,
                tenant_id,
                title=title,
                raw_text=raw_text,
                content_hash=digest,
                created_by=user_id,
            )
            if created is not None:
                return created, True
            existing = await documents_repo.get_by_hash(session, tenant_id, digest)
            if existing is None:
                continue
            if existing.status == FAILED:
                existing = await documents_repo.set_status(
                    session, tenant_id, existing.id, PENDING
                )
                assert existing is not None
            return existing, False
    raise DocumentNotFound("document disappeared during creation")


async def ingest_document(
    tenant_id: uuid.UUID, document_id: uuid.UUID, provider: EmbeddingProvider
) -> Document:
    """Chunk, embed and store ``document_id``; it ends READY or FAILED.

    Raises DocumentNotFound (no side effects) for an unknown document or one
    of another tenant, and IngestionError after recording FAILED.
    """
    async with tenant_transaction(tenant_id) as session:
        document = await documents_repo.get(session, tenant_id, document_id)
        if document is None:
            raise DocumentNotFound("document not found")
        if document.status == READY and await chunks_repo.count_for_document(
            session, tenant_id, document_id
        ):
            return document
        raw_text = document.raw_text

    try:
        return await _embed_and_store(tenant_id, document_id, raw_text, provider)
    except DocumentNotFound:
        raise
    except Exception as exc:
        logger.exception("ingestion of document %s failed", document_id)
        await _mark_failed(tenant_id, document_id, exc)
        raise IngestionError("ingestion failed") from exc


async def _embed_and_store(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    raw_text: str,
    provider: EmbeddingProvider,
) -> Document:
    # No transaction is open here: chunking and embedding may take a while.
    pieces = chunk_text(raw_text)
    if not pieces:
        raise EmptyDocument("document produced no chunks")
    vectors = await provider.embed_passages([piece["text"] for piece in pieces])
    # Re-checked against the column size: a provider may skip validation.
    vectors = validate_vectors(vectors, count=len(pieces), dim=EMBEDDING_DIM)

    async with tenant_transaction(tenant_id) as session:
        document = await documents_repo.get_for_update(session, tenant_id, document_id)
        if document is None:
            raise DocumentNotFound("document not found")
        # Another worker finished while we were embedding: keep its chunks.
        if document.status == READY and await chunks_repo.count_for_document(
            session, tenant_id, document_id
        ):
            return document
        await chunks_repo.delete_for_document(session, tenant_id, document_id)
        await chunks_repo.insert_many(
            session,
            tenant_id,
            document_id,
            [
                {
                    "chunk_index": piece["index"],
                    "content": piece["text"],
                    "char_start": piece["start"],
                    "char_end": piece["end"],
                    "embedding": vector,
                }
                for piece, vector in zip(pieces, vectors, strict=True)
            ],
            embedding_model=provider.model_name,
        )
        ready = await documents_repo.set_status(session, tenant_id, document_id, READY)
        assert ready is not None
        return ready


async def _mark_failed(
    tenant_id: uuid.UUID, document_id: uuid.UUID, exc: BaseException
) -> None:
    """Record FAILED in its own transaction; never masks the original error.

    A document another worker already made READY is left alone: this
    attempt's failure does not invalidate that worker's chunks.
    """
    try:
        async with tenant_transaction(tenant_id) as session:
            document = await documents_repo.get_for_update(
                session, tenant_id, document_id
            )
            if document is None or document.status == READY:
                return
            await documents_repo.set_status(
                session, tenant_id, document_id, FAILED, error=error_summary(exc)
            )
    except Exception:
        logger.exception("could not mark document %s as FAILED", document_id)


async def list_documents(
    tenant_id: uuid.UUID, *, limit: int = DEFAULT_LIMIT, offset: int = 0
) -> list[Document]:
    async with tenant_transaction(tenant_id) as session:
        return await documents_repo.list_for_tenant(
            session,
            tenant_id,
            limit=max(1, min(limit, MAX_LIMIT)),
            offset=max(0, offset),
        )
