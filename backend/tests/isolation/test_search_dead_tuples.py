"""Regression: dead HNSW entries make a small tenant unreachable; the exact
fallback must still return its chunks.

Reproduces the Day 3 diagnosis (docs/plans/day-03.md, "HNSW dead tuples"):
churning 200 near-identical B vectors without VACUUM leaves tenant A's
far-away nodes unreachable from the graph's entry point.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.repositories.chunks import (
    CHUNKS_EMBEDDING_INDEX,
    explain_statement,
    vector_search,
    vector_search_statement,
)
from app.db.tenant_context import set_tenant
from app.services.search import search_in_session
from tests.conftest import (
    SeededTenant,
    insert_chunk,
    insert_chunks,
    insert_document,
    unit_vector,
)
from tests.isolation.conftest import gather_diagnostics

Q = unit_vector(1.0)
CHURN_STEP = 2  # delete+reinsert rounds between precondition probes
MAX_CHURN_ROUNDS = 40  # bound; reaching it fails loudly with stats, never skips
B_VECTORS = [unit_vector(1.0, 0.001 * (i + 1)) for i in range(200)]


def _owner_engine():
    return create_async_engine(
        settings.migration_database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )


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


async def _probe(app_conn: AsyncConnection, ta: SeededTenant) -> tuple[list, list[str]]:
    """Raw ANN hits and the EXPLAIN of the very statement the service runs."""
    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, ta["id"])
        # Test-only: pins the HNSW plan (see tests/isolation/conftest.py).
        await session.execute(text("SET LOCAL enable_sort = off"))
        plan = [
            row[0]
            for row in await session.execute(
                explain_statement(vector_search_statement(ta["id"], Q, 3))
            )
        ]
        raw = await vector_search(session, ta["id"], Q, 3)
    return raw, plan


async def _churn(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    ta: SeededTenant,
    tb: SeededTenant,
) -> tuple[set[uuid.UUID], int]:
    """Seed, then churn B in rounds of CHURN_STEP until A's graph is unreachable.

    Returns A's chunk ids and the number of rounds it took. After each step
    ANALYZE runs so the planner statistics are deterministic. At the bound the
    test fails loudly with the table/index stats.
    """
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
    for done in range(CHURN_STEP, MAX_CHURN_ROUNDS + 1, CHURN_STEP):
        for _ in range(CHURN_STEP):
            await owner_conn.execute(delete_b, {"doc": doc_b})
            await owner_conn.commit()
            await insert_chunks(owner_conn, tb["id"], doc_b, B_VECTORS)
            await owner_conn.commit()
        await _owner_autocommit("ANALYZE chunks")
        raw, _plan = await _probe(app_conn, ta)
        if raw == []:
            return a_ids, done
    engine = _owner_engine()
    try:
        async with engine.connect() as diag_conn:
            stats = await gather_diagnostics(diag_conn)
    finally:
        await engine.dispose()
    pytest.fail(
        f"CHURN BOUND REACHED: {MAX_CHURN_ROUNDS} rounds did not make A's chunks "
        f"unreachable (last raw ANN hits: {len(raw)}). Stats: {stats}",
        pytrace=False,
    )


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
        a_ids, _rounds = await _churn(owner_conn, app_conn, ta, tb)

        async with AsyncSession(bind=app_conn) as session:
            await set_tenant(session, ta["id"])
            # Test-only: pins the HNSW plan (see tests/isolation/conftest.py).
            await session.execute(text("SET LOCAL enable_sort = off"))
            # The precondition below only means something if the raw ANN
            # statement goes through the HNSW index, not the tenant btree.
            plan = "\n".join(
                row[0]
                for row in await session.execute(
                    explain_statement(vector_search_statement(ta["id"], Q, 3))
                )
            )
            assert CHUNKS_EMBEDDING_INDEX in plan, plan
            assert "ix_chunks_tenant_id" not in plan, plan
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
