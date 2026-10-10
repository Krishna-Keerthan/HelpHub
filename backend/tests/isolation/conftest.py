"""Hermetic HNSW state for the ANN search tests.

Dead index entries left by earlier tests can make HNSW lose its paths to a
small tenant (see docs/plans/day-03.md, "HNSW dead tuples"). The modules
below therefore start from a vacuumed chunks table.

test_search_isolation is an unedited spec module whose ANN test only sets
enable_seqscan = off. With ix_chunks_tenant_id present the planner then picks
the tenant btree + sort instead of HNSW, so this fixture also sets the one
test-only planner flag that pins HNSW for it (enable_sort = off). Production
code never sets planner flags.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

HERMETIC_MODULES = {"test_search_isolation", "test_search_hermetic"}
# Test-only planner flags per module; kept to the minimum that pins HNSW.
PLANNER_FLAGS = {"test_search_isolation": ("enable_sort",)}


async def vacuum_chunks() -> None:
    """VACUUM needs autocommit (it cannot run inside a transaction)."""
    engine = create_async_engine(
        settings.migration_database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("VACUUM chunks"))
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def hermetic_chunks(request: pytest.FixtureRequest) -> None:
    """Autouse, so it runs before app_conn (and any test transaction)."""
    if _module(request) in HERMETIC_MODULES:
        await vacuum_chunks()


@pytest.fixture
async def app_conn(
    hermetic_chunks: None, app_conn: AsyncConnection, request: pytest.FixtureRequest
) -> AsyncConnection:
    """The root app_conn, plus this module's test-only planner flags.

    Session level and committed before the test runs, so they survive the
    test's own transactions; the connection is discarded after the test.
    """
    flags = PLANNER_FLAGS.get(_module(request), ())
    for flag in flags:
        await app_conn.execute(text(f"SET {flag} = off"))
    if flags:
        await app_conn.commit()
    return app_conn


def _module(request: pytest.FixtureRequest) -> str:
    return request.module.__name__.rsplit(".", 1)[-1]
