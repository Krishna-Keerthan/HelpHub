import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import documents as documents_service
from app.services.embeddings import FakeEmbeddingProvider
from tests.conftest import SeededTenant
from tests.ingestion_helpers import CONTENT, SpyProvider, owner_chunks, owner_document

Tenants = dict[str, SeededTenant]


@pytest.mark.parametrize("ingest_first", [False, True], ids=["pending", "ready"])
async def test_ingest_other_tenants_document_is_not_found(
    owner_conn: AsyncConnection, two_tenants_seeded: Tenants, ingest_first: bool
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    document, _ = await documents_service.create_or_get(
        ta["id"], ta["user_id"], "A's doc", CONTENT
    )
    if ingest_first:
        await documents_service.ingest_document(
            ta["id"], document.id, FakeEmbeddingProvider()
        )
    doc_before = await owner_document(owner_conn, document.id)
    chunks_before = await owner_chunks(owner_conn, document.id)
    spy = SpyProvider()

    with pytest.raises(documents_service.DocumentNotFound):
        await documents_service.ingest_document(tb["id"], document.id, spy)

    assert spy.calls == 0
    assert await owner_document(owner_conn, document.id) == doc_before
    assert await owner_chunks(owner_conn, document.id) == chunks_before
    assert bool(chunks_before) is ingest_first


async def test_ingest_unknown_document_is_not_found(
    two_tenants_seeded: Tenants,
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    spy = SpyProvider()
    with pytest.raises(documents_service.DocumentNotFound):
        await documents_service.ingest_document(ta["id"], uuid.uuid4(), spy)
    assert spy.calls == 0
