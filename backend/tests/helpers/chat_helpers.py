"""Shared seeding and readers for the chat tests."""

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import Principal
from app.db.session import engine
from app.services.embeddings import FakeEmbeddingProvider
from tests.conftest import SeededTenant, insert_chunk, insert_document, unit_vector


class AxisQueryEmbedder(FakeEmbeddingProvider):
    """Every query embeds to the first axis, so chunk scores are chosen."""

    async def embed_query(self, text: str) -> list[float]:
        return unit_vector(1.0)


class BrokenEmbedder(FakeEmbeddingProvider):
    MESSAGE = "EMBED-SECRET-TEXT upstream said no"

    async def embed_query(self, text: str) -> list[float]:
        raise RuntimeError(self.MESSAGE)


def principal_of(tenant: SeededTenant) -> Principal:
    return Principal(user_id=tenant["user_id"], tenant_id=tenant["id"], role="admin")


def with_score(score: float) -> list[float]:
    return unit_vector(score, (1 - score**2) ** 0.5)


async def seed_chunk(
    owner_conn: AsyncConnection,
    tenant: SeededTenant,
    score: float = 0.9,
    content: str = "Reset your password in Settings.",
) -> uuid.UUID:
    document_id = await insert_document(
        owner_conn, tenant["id"], created_by=tenant["user_id"], title="Guide"
    )
    chunk_id = await insert_chunk(
        owner_conn,
        tenant["id"],
        document_id,
        content=content,
        embedding=with_score(score),
    )
    await owner_conn.commit()
    return chunk_id


async def message_rows(owner_conn: AsyncConnection, tenant_id: uuid.UUID) -> list[Any]:
    result = await owner_conn.execute(
        text(
            "SELECT conversation_id, role, content, status, sources, model "
            "FROM chat_messages WHERE tenant_id = :t ORDER BY seq"
        ),
        {"t": tenant_id},
    )
    rows = list(result.mappings())
    await owner_conn.rollback()
    return rows


def checked_out_connections() -> int:
    """Connections the runtime pool currently has lent out."""
    return engine.pool.checkedout()  # type: ignore[attr-defined]
