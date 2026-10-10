import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import documents as documents_service
from app.services.chunker import chunk_text
from app.services.embeddings import FakeEmbeddingProvider
from tests.conftest import MakeTenant, insert_chunk
from tests.ingestion_helpers import CONTENT, FailingProvider, owner_chunks


async def test_retry_after_failure_reuses_document(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    first, created = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    assert created is True
    with pytest.raises(documents_service.IngestionError):
        await documents_service.ingest_document(
            tenant["id"], first.id, FailingProvider()
        )

    again, created = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    assert created is False
    assert again.id == first.id
    assert again.status == "PENDING"
    assert again.error is None

    ready = await documents_service.ingest_document(
        tenant["id"], again.id, FakeEmbeddingProvider()
    )
    assert ready.status == "READY"
    assert ready.error is None
    chunks = await owner_chunks(owner_conn, first.id)
    assert [c["chunk_index"] for c in chunks] == list(
        range(len(chunk_text(first.raw_text)))
    )


async def test_reingest_replaces_stale_chunks(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    """Chunks left by an earlier attempt are replaced, never duplicated."""
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    for i in range(2):
        await insert_chunk(
            owner_conn, tenant["id"], document.id, chunk_index=i, content="stale"
        )
    await owner_conn.commit()

    await documents_service.ingest_document(
        tenant["id"], document.id, FakeEmbeddingProvider()
    )

    chunks = await owner_chunks(owner_conn, document.id)
    assert len(chunks) == len(chunk_text(document.raw_text))
    assert all(c["text"] != "stale" for c in chunks)
