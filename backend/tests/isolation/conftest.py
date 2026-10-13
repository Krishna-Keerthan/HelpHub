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

import asyncio
import concurrent.futures
import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

HERMETIC_MODULES = {"test_search_isolation", "test_search_hermetic"}
# Test-only planner flags per module; kept to the minimum that pins HNSW.
PLANNER_FLAGS = {"test_search_isolation": ("enable_sort",)}


VACUUM_ATTEMPTS = 5
VACUUM_RETRY_SLEEP = 0.5
# Tests whose failures get the HNSW evidence dump attached (tests stay unedited).
EVIDENCE_TESTS = {
    "test_search_dead_tuples",
    "test_search_hermetic",
    "test_filtered_ann_with_hnsw",
}

_ACTIVITY_SQL = text(
    "SELECT pid, application_name, state, xact_start, backend_xmin::text, "
    "left(query, 80) FROM pg_stat_activity "
    "WHERE datname = current_database() AND pid <> pg_backend_pid() "
    "AND (state = 'idle in transaction' OR backend_xmin IS NOT NULL)"
)
_STATS_SQL = text(
    "SELECT n_live_tup, n_dead_tup, last_vacuum, last_autovacuum, last_analyze, "
    "last_autoanalyze FROM pg_stat_user_tables WHERE relname = 'chunks'"
)


def _owner_engine():
    return create_async_engine(
        settings.migration_database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )


async def _dead_tuples(conn: AsyncConnection) -> int:
    await conn.execute(text("SELECT pg_stat_force_next_flush()"))
    return (await conn.execute(_STATS_SQL)).one()[1]


async def gather_diagnostics(conn: AsyncConnection) -> dict:
    """Evidence about the chunks table and its HNSW index; no row data values."""
    activity = [
        dict(
            zip(
                ("pid", "app", "state", "xact_start", "backend_xmin", "query"),
                map(str, row),
                strict=True,
            )
        )
        for row in await conn.execute(_ACTIVITY_SQL)
    ]
    await conn.execute(text("SELECT pg_stat_force_next_flush()"))
    stats = (await conn.execute(_STATS_SQL)).one()
    sizes = (
        await conn.execute(
            text(
                "SELECT pg_relation_size('chunks'), "
                "pg_relation_size('ix_chunks_embedding_hnsw'), "
                "(SELECT reloptions::text FROM pg_class "
                "WHERE oid = 'public.chunks'::regclass)"
            )
        )
    ).one()
    return {
        "other_backends_holding_snapshots": activity,
        "n_live_tup": stats[0],
        "n_dead_tup": stats[1],
        "last_vacuum": str(stats[2]),
        "last_autovacuum": str(stats[3]),
        "last_analyze": str(stats[4]),
        "last_autoanalyze": str(stats[5]),
        "chunks_bytes": sizes[0],
        "hnsw_bytes": sizes[1],
        "reloptions": sizes[2],
    }


async def vacuum_chunks() -> dict:
    """VACUUM chunks and PROVE the table is clean (n_dead_tup == 0).

    Retries a few times (stats lag, short-lived snapshots); then fails with the
    evidence instead of letting tests run on a dirty HNSW graph. Returns the
    diagnostics gathered before the first VACUUM.
    """
    engine = _owner_engine()
    try:
        async with engine.connect() as conn:
            before = await gather_diagnostics(conn)
            notices: list[str] = []
            raw = (await conn.get_raw_connection()).driver_connection
            raw.add_log_listener(lambda _c, message: notices.append(str(message)))
            dead = -1
            for _attempt in range(VACUUM_ATTEMPTS):
                await conn.execute(text("VACUUM (VERBOSE) chunks"))
                dead = await _dead_tuples(conn)
                if dead == 0:
                    return before
                await asyncio.sleep(VACUUM_RETRY_SLEEP)
            after = await gather_diagnostics(conn)
            pytest.fail(
                f"hermetic fixture: chunks still has n_dead_tup={dead} after "
                f"{VACUUM_ATTEMPTS} VACUUMs; tests would run on a dirty graph.\n"
                + json.dumps(
                    {"before": before, "after": after, "vacuum_verbose": notices[-40:]},
                    indent=2,
                    default=str,
                ),
                pytrace=False,
            )
    finally:
        await engine.dispose()


async def _evidence_text() -> str:
    engine = _owner_engine()
    try:
        async with engine.connect() as conn:
            return json.dumps(await gather_diagnostics(conn), indent=2, default=str)
    finally:
        await engine.dispose()


def _evidence_in_thread() -> str:
    """Fresh owner connection on its own loop (the test loop is not running here)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_evidence_text())).result(timeout=60)


def _wants_evidence(item: pytest.Item) -> bool:
    return item.name in EVIDENCE_TESTS or _module(item) in EVIDENCE_TESTS


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Attach HNSW evidence to failures of the dead-tuple/hermetic ANN tests."""
    outcome = yield
    report = outcome.get_result()
    if report.failed and _wants_evidence(item):
        try:
            report.sections.append(
                ("HNSW evidence (at failure)", _evidence_in_thread())
            )
        except Exception as exc:  # noqa: BLE001 - diagnostics must never mask the failure
            report.sections.append(
                ("HNSW evidence (at failure)", f"unavailable: {type(exc).__name__}")
            )


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


def _module(request: pytest.FixtureRequest | pytest.Item) -> str:
    return request.module.__name__.rsplit(".", 1)[-1]
