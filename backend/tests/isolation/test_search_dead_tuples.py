"""Regression: dead HNSW entries make a small tenant unreachable; the exact
fallback must still return its chunks.

Reproduces the Day 3 diagnosis (docs/plans/day-03.md, "HNSW dead tuples"):
churning 200 near-identical B vectors without VACUUM leaves tenant A's
far-away nodes unreachable from the graph's entry point.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.repositories.chunks import vector_search
from app.db.tenant_context import set_tenant
from app.services.search import search_in_session
from tests.conftest import (
    SeededTenant,
    insert_chunk,
    insert_chunks,
    insert_document,
    unit_vector,
)

Q = unit_vector(1.0)
CHURN_ROUNDS = 12
B_VECTORS = [unit_vector(1.0, 0.001 * (i + 1)) for i in range(200)]


async def _owner_autocommit(*statements: str) -> None:
    engine = create_async_engine(
        settings.migration_database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as conn:
            for statement in statements:
                await conn.execute(text(statement))
    finally:
        await engine.dispose()


async def _reloptions(owner_conn: AsyncConnection) -> list[str] | None:
    await owner_conn.rollback()  # never let an earlier failure mask this check
    result = await owner_conn.execute(
        text("SELECT reloptions FROM pg_class WHERE oid = 'public.chunks'::regclass")
    )
    value = result.scalar_one()
    await owner_conn.rollback()
    return value


async def _churn(
    owner_conn: AsyncConnection, ta: SeededTenant, tb: SeededTenant
) -> set[uuid.UUID]:
    doc_a = await insert_document(owner_conn, ta["id"], created_by=ta["user_id"])
    doc_b = await insert_document(owner_conn, tb["id"], created_by=tb["user_id"])
    await insert_chunks(owner_conn, tb["id"], doc_b, B_VECTORS)
    a_ids = {
        await insert_chunk(
            owner_conn,
            ta["id"],
            doc_a,
            chunk_index=i,
            embedding=unit_vector(0.0, 1.0, 0.1 * (i + 1)),
        )
        for i in range(3)
    }
    await owner_conn.commit()
    # Each round leaves 200 dead B entries in the HNSW graph (no VACUUM).
    delete_b = text("DELETE FROM chunks WHERE document_id = :doc")
    for _ in range(CHURN_ROUNDS):
        await owner_conn.execute(delete_b, {"doc": doc_b})
        await owner_conn.commit()
        await insert_chunks(owner_conn, tb["id"], doc_b, B_VECTORS)
        await owner_conn.commit()
    return a_ids


async def test_dead_tuples_fallback_returns_small_tenant(
    owner_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
    app_conn: AsyncConnection,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    try:
        await _owner_autocommit(
            "ALTER TABLE chunks SET (autovacuum_enabled = false)",
            "REINDEX INDEX ix_chunks_embedding_hnsw",
        )
        a_ids = await _churn(owner_conn, ta, tb)

        async with AsyncSession(bind=app_conn) as session:
            await set_tenant(session, ta["id"])
            # Test-only: pins the HNSW plan (see tests/isolation/conftest.py).
            await session.execute(text("SET LOCAL enable_sort = off"))
            raw = await vector_search(session, ta["id"], Q, 3)
            assert raw == [], (
                "PRECONDITION FAILED: churn did not reproduce the unreachable-"
                f"graph state (raw ANN returned {len(raw)} hits); this test "
                "would not exercise the fallback"
            )
            result = await search_in_session(session, ta["id"], Q, 3)

        assert {hit.chunk_id for hit in result.hits} == a_ids
        assert result.used_fallback is True
    finally:
        await _owner_autocommit(
            "ALTER TABLE chunks RESET (autovacuum_enabled)", "VACUUM chunks"
        )
        assert await _reloptions(owner_conn) is None
