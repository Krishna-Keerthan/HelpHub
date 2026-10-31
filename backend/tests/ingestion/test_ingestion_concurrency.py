import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.models import Document
from app.db.repositories import documents as documents_repo
from app.services import documents as documents_service
from app.services.chunker import chunk_text
from app.services.embeddings import FakeEmbeddingProvider
from tests.conftest import MakeTenant
from tests.helpers.ingestion_helpers import CONTENT, owner_chunks, owner_document

BARRIER_TIMEOUT = 5.0
# How long the first lock holder waits for the other worker to also read the
# row. With FOR UPDATE the other worker is blocked on the lock, so this
# expires; without it both read PENDING and the race is forced.
OVERLAP_WAIT = 0.5


async def test_concurrent_ingest_produces_one_set_of_chunks(
    monkeypatch: pytest.MonkeyPatch,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    original = documents_repo.get_for_update
    both_embedded = asyncio.Barrier(2)
    both_read = asyncio.Event()
    observed: list[str] = []

    async def gated_get_for_update(
        session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        # Both workers have finished steps 1-2 (read + embed) before either
        # starts the write transaction.
        await asyncio.wait_for(both_embedded.wait(), BARRIER_TIMEOUT)
        row = await original(session, tenant_id, document_id)
        assert row is not None
        observed.append(row.status)
        if len(observed) == 2:
            both_read.set()
        try:
            await asyncio.wait_for(both_read.wait(), OVERLAP_WAIT)
        except TimeoutError:
            pass
        return row

    monkeypatch.setattr(documents_repo, "get_for_update", gated_get_for_update)
    provider = FakeEmbeddingProvider()

    results = await asyncio.gather(
        documents_service.ingest_document(tenant["id"], document.id, provider),
        documents_service.ingest_document(tenant["id"], document.id, provider),
        return_exceptions=True,
    )

    assert not [r for r in results if isinstance(r, BaseException)], results
    # The lock serialised them: the second saw the first one's committed READY.
    assert sorted(observed) == ["PENDING", "READY"]
    chunks = await owner_chunks(owner_conn, document.id)
    assert [c["chunk_index"] for c in chunks] == list(
        range(len(chunk_text(document.raw_text)))
    )
    row = await owner_document(owner_conn, document.id)
    assert row is not None and row["status"] == "READY"
