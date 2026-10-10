"""Providers and owner-side readers shared by the ingestion tests."""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.session import APPLICATION_NAME
from app.services.embeddings import FakeEmbeddingProvider

# Several paragraphs (with \r\n and runs of blank lines) so the chunker
# produces more than one chunk and offsets are exercised.
CONTENT = (
    "\r\n\r\n".join(
        f"Paragraph {i}: " + "Ingestion keeps exact offsets into raw text. " * 15
        for i in range(5)
    )
    + "\n\n\n\nTrailing section.\n"
)

IDLE_IN_TRANSACTION_SQL = text(
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE usename = 'helphub_app' AND datname = current_database() "
    "AND application_name = :app AND state LIKE 'idle in transaction%'"
)


async def idle_in_transaction(owner_conn: AsyncConnection) -> int:
    """This process's app sessions currently idle inside an open transaction.

    Filtered on the runtime engine's application_name, so other clients of
    the shared dev database cannot make the spy tests fail.
    """
    count = (
        await owner_conn.execute(IDLE_IN_TRANSACTION_SQL, {"app": APPLICATION_NAME})
    ).scalar_one()
    await owner_conn.rollback()
    return count


class SpyProvider(FakeEmbeddingProvider):
    """Fake provider that runs ``on_embed`` inside every embed_passages call."""

    def __init__(self, on_embed: Callable[[], Awaitable[None]] | None = None):
        self.on_embed = on_embed
        self.calls = 0

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.on_embed is not None:
            await self.on_embed()
        return await super().embed_passages(texts)


class QuerySpyProvider(FakeEmbeddingProvider):
    """Fake provider that runs ``on_embed`` inside every embed_query call."""

    def __init__(self, on_embed: Callable[[], Awaitable[None]] | None = None):
        self.on_embed = on_embed
        self.query_calls = 0

    async def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        if self.on_embed is not None:
            await self.on_embed()
        return await super().embed_query(text)


class FailingProvider(FakeEmbeddingProvider):
    # The message mimics a third-party error carrying content; it must not
    # be stored.
    MESSAGE = "model crashed while embedding: Paragraph 0: Ingestion keeps"

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        raise RuntimeError(self.MESSAGE)


class WrongCountProvider(FakeEmbeddingProvider):
    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return (await super().embed_passages(texts))[:-1]


class WrongDimProvider(FakeEmbeddingProvider):
    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [vec[:-1] for vec in await super().embed_passages(texts)]


async def owner_document(
    owner_conn: AsyncConnection, document_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await owner_conn.execute(
        text(
            "SELECT id, tenant_id, status, error, raw_text, content_hash, "
            "created_by, updated_at FROM documents WHERE id = :id"
        ),
        {"id": document_id},
    )
    row = result.mappings().one_or_none()
    await owner_conn.rollback()
    return dict(row) if row is not None else None


async def owner_chunks(
    owner_conn: AsyncConnection, document_id: uuid.UUID
) -> list[dict[str, Any]]:
    result = await owner_conn.execute(
        text(
            "SELECT id, tenant_id, chunk_index, text, char_start, char_end, "
            "embedding_model FROM chunks WHERE document_id = :id "
            "ORDER BY chunk_index"
        ),
        {"id": document_id},
    )
    rows = [dict(row) for row in result.mappings()]
    await owner_conn.rollback()
    return rows
