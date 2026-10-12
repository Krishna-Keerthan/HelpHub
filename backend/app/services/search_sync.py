"""Keeps the Elasticsearch copy of a document's chunks in step with Postgres.

Postgres is the source of truth and its ``status`` is never touched here: an
ES failure only sets ``search_index_status`` to FAILED (class name recorded,
never ES text). Reads and writes to Postgres use short transactions that are
closed before ES is called.
"""

import logging
import uuid
from collections.abc import Iterator
from typing import Any

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.core.config import settings
from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.db.tenant_context import tenant_transaction
from app.services import es_index
from app.services.es_client import alias_name

logger = logging.getLogger(__name__)

PENDING = "PENDING"
INDEXED = "INDEXED"
FAILED = "FAILED"
BULK_CHUNK_SIZE = 500
# A bulk of ~500 chunks takes longer than one search.
BULK_TIMEOUT_FACTOR = 3


class BulkIndexError(Exception):
    """Some chunks were rejected by Elasticsearch (count only)."""


def _actions(
    index: str,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    title: str,
    chunks: list[tuple[uuid.UUID, int, str]],
) -> Iterator[dict[str, Any]]:
    for chunk_id, chunk_index, content in chunks:
        yield {
            "_op_type": "index",
            "_index": index,
            "_id": str(chunk_id),
            "_source": {
                "tenant_id": str(tenant_id),
                "document_id": str(document_id),
                "chunk_index": chunk_index,
                "title": title,
                "content": content,
            },
        }


async def index_document(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    es: AsyncElasticsearch,
    *,
    index: str | None = None,
) -> bool:
    """Index one document's chunks (``_id`` = chunk id); True when INDEXED.

    Never raises for ES or indexing problems; a missing document is a no-op.
    ``index`` defaults to the alias (the reindex script targets a new version).
    """
    async with tenant_transaction(tenant_id) as session:
        titles = await documents_repo.titles_for(session, tenant_id, [document_id])
        chunks = await chunks_repo.list_for_indexing(session, tenant_id, document_id)
    if document_id not in titles:
        return False
    # No Postgres transaction is open from here until the status update.
    try:
        if index is None:
            await es_index.ensure_index(es)
        target = index or alias_name()
        client = es.options(
            request_timeout=settings.es_timeout_seconds * BULK_TIMEOUT_FACTOR
        )
        _, failed = await async_bulk(
            client,
            _actions(target, tenant_id, document_id, titles[document_id], chunks),
            chunk_size=BULK_CHUNK_SIZE,
            raise_on_error=False,
            raise_on_exception=True,
            stats_only=True,
        )
        if failed:
            raise BulkIndexError(f"{failed} chunks rejected")
    except Exception as exc:  # noqa: BLE001 - any ES failure is recorded, not raised
        logger.warning(
            "search indexing failed: %s tenant=%s document=%s",
            type(exc).__name__,
            tenant_id,
            document_id,
        )
        await _record(tenant_id, document_id, FAILED, type(exc).__name__)
        return False
    await _record(tenant_id, document_id, INDEXED, None)
    return True


async def _record(
    tenant_id: uuid.UUID, document_id: uuid.UUID, state: str, error: str | None
) -> None:
    try:
        async with tenant_transaction(tenant_id) as session:
            await documents_repo.set_search_index_status(
                session, tenant_id, document_id, state, error=error
            )
    except Exception as exc:  # noqa: BLE001 - must not fail the caller
        logger.warning(
            "could not record search_index_status: %s tenant=%s document=%s",
            type(exc).__name__,
            tenant_id,
            document_id,
        )


async def delete_document_chunks(
    tenant_id: uuid.UUID, document_id: uuid.UUID, es: AsyncElasticsearch
) -> None:
    """Remove a deleted document's chunks; failures are logged, never raised."""
    try:
        # delete_by_query only sees refreshed documents; a document deleted
        # right after it was indexed would otherwise keep its chunks in ES.
        await es.indices.refresh(index=alias_name())
        await es.delete_by_query(
            index=alias_name(),
            query={
                "bool": {
                    "filter": [
                        {"term": {"tenant_id": str(tenant_id)}},
                        {"term": {"document_id": str(document_id)}},
                    ]
                }
            },
            conflicts="proceed",
        )
    except Exception as exc:  # noqa: BLE001 - the database delete already happened
        logger.warning(
            "search delete failed: %s tenant=%s document=%s",
            type(exc).__name__,
            tenant_id,
            document_id,
        )
