"""Helpers for tests that use the real Elasticsearch (never skipped: they fail
clearly, with a short timeout, when ES is unreachable)."""

import uuid
from typing import Any

from elasticsearch import AsyncElasticsearch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import es_index
from app.services.es_client import alias_name
from tests.conftest import SeededTenant, auth_headers
from tests.helpers.ingestion_helpers import owner_chunks


async def index_raw(
    es: AsyncElasticsearch,
    *,
    chunk_id: uuid.UUID,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    content: str,
    title: str = "t",
    chunk_index: int = 0,
    refresh: bool = True,
) -> None:
    """Index one ES document exactly as given (may be deliberately wrong)."""
    await es_index.ensure_index(es)
    await es.index(
        index=alias_name(),
        id=str(chunk_id),
        document={
            "tenant_id": str(tenant_id),
            "document_id": str(document_id),
            "chunk_index": chunk_index,
            "title": title,
            "content": content,
        },
    )
    if refresh:
        await es.indices.refresh(index=alias_name())


async def upload(
    client: AsyncClient, tenant: SeededTenant, title: str, content: str
) -> uuid.UUID:
    response = await client.post(
        "/documents",
        json={"title": title, "content": content},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


async def upload_and_index(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    es: AsyncElasticsearch,
    tenant: SeededTenant,
    title: str,
    content: str,
) -> tuple[uuid.UUID, list[dict[str, Any]]]:
    """Upload through the API, then index its Postgres chunks into ES."""
    document_id = await upload(client, tenant, title, content)
    rows = await owner_chunks(owner_conn, document_id)
    for row in rows:
        await index_raw(
            es,
            chunk_id=row["id"],
            tenant_id=tenant["id"],
            document_id=document_id,
            content=row["text"],
            title=title,
            chunk_index=row["chunk_index"],
            refresh=False,
        )
    await es.indices.refresh(index=alias_name())
    return document_id, rows


def dead_client() -> AsyncElasticsearch:
    """A client for an unreachable ES (connection refused, no retries)."""
    return AsyncElasticsearch("http://127.0.0.1:1", request_timeout=0.5, max_retries=0)


async def doc_index_state(
    owner_conn: AsyncConnection, document_id: uuid.UUID
) -> dict[str, Any]:
    from sqlalchemy import text

    result = await owner_conn.execute(
        text(
            "SELECT status, search_index_status, search_index_error "
            "FROM documents WHERE id = :id"
        ),
        {"id": document_id},
    )
    row = dict(result.mappings().one())
    await owner_conn.rollback()
    return row


async def es_ids(
    es: AsyncElasticsearch,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
) -> set[str]:
    """Ids of ES documents claiming ``tenant_id`` (and ``document_id``)."""
    await es.indices.refresh(index=alias_name())
    filters: list[dict[str, Any]] = [{"term": {"tenant_id": str(tenant_id)}}]
    if document_id is not None:
        filters.append({"term": {"document_id": str(document_id)}})
    response = await es.search(
        index=alias_name(), query={"bool": {"filter": filters}}, size=1000, source=False
    )
    return {hit["_id"] for hit in response["hits"]["hits"]}
