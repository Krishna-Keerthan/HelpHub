from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import documents as documents_service
from app.services.chunker import chunk_text
from app.services.embeddings import FakeEmbeddingProvider
from tests.conftest import MakeTenant
from tests.helpers.ingestion_helpers import CONTENT, owner_chunks, owner_document


async def test_stored_chunks_match_raw_text_offsets(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    provider = FakeEmbeddingProvider()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    await documents_service.ingest_document(tenant["id"], document.id, provider)

    row = await owner_document(owner_conn, document.id)
    assert row is not None
    raw_text = row["raw_text"]
    assert raw_text == CONTENT  # \r\n and blank-line runs are stored as-is
    chunks = await owner_chunks(owner_conn, document.id)

    assert len(chunks) > 1
    assert len(chunks) == len(chunk_text(raw_text))
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    for chunk in chunks:
        assert raw_text[chunk["char_start"] : chunk["char_end"]] == chunk["text"]
        assert chunk["embedding_model"] == provider.model_name
        assert chunk["tenant_id"] == tenant["id"]
