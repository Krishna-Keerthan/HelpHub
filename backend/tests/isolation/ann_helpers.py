"""Reachability precondition for ANN tests that assert ``used_fallback is False``.

HNSW recall for an outlier tenant is probabilistic (random levels, pruning;
AR-15). A test that wants the pure ANN path to find a tenant's chunks first
proves, with an independent probe, that the graph can reach them at all. A graph
that cannot is rebuilt (REINDEX); at the bound the test fails with evidence.
It never skips.
"""

import json
import uuid
from collections.abc import Sequence

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

MAX_ATTEMPTS = 8
PROBE_EF_SEARCH = 1000  # pgvector's maximum

# Last probe inputs, read by the failure-time evidence hook (conftest.py).
LAST_PROBE: dict[str, object] = {}

_PROBE_SQL = text(
    "SELECT id FROM chunks ORDER BY embedding <=> CAST(:probe AS vector) LIMIT 300"
)


def _literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


async def probe_reachability(
    conn: AsyncConnection,
    target_ids: Sequence[uuid.UUID],
    probe_vector: Sequence[float],
) -> tuple[bool, int, int]:
    """(all targets found, rows returned, targets found) from an independent probe.

    Runs on an owner connection (RLS bypass), without iterative scan and with
    the largest ef_search, so it measures graph reachability alone. Ends the
    connection's transaction so nothing blocks a later REINDEX.
    """
    try:
        await conn.execute(text("SET LOCAL hnsw.ef_search = 1000"))
        await conn.execute(text("SET LOCAL hnsw.iterative_scan = off"))
        effective = (
            await conn.execute(text("SELECT current_setting('hnsw.ef_search')"))
        ).scalar_one()
        if effective != "1000":  # SET LOCAL is a no-op on an autocommit connection
            raise RuntimeError("probe needs a transactional connection")
        rows = await conn.execute(_PROBE_SQL, {"probe": _literal(probe_vector)})
        ids = {row[0] for row in rows}
    finally:
        await conn.rollback()
    wanted = {uuid.UUID(str(t)) for t in target_ids}
    found = len(wanted & ids)
    return found == len(wanted), len(ids), found


async def _reindex() -> None:
    engine = create_async_engine(
        settings.migration_database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("REINDEX INDEX ix_chunks_embedding_hnsw"))
    finally:
        await engine.dispose()


async def _diagnostics(conn: AsyncConnection, sizes: list[tuple[int, int]]) -> dict:
    row = (
        await conn.execute(
            text(
                "SELECT (SELECT extversion FROM pg_extension WHERE extname = 'vector'), "
                "(SELECT n_live_tup FROM pg_stat_user_tables WHERE relname = 'chunks'), "
                "pg_relation_size('ix_chunks_embedding_hnsw'), "
                "(SELECT reloptions::text FROM pg_class "
                "WHERE oid = 'public.chunks'::regclass)"
            )
        )
    ).one()
    await conn.rollback()
    return {
        "pgvector": row[0],
        "n_live_tup": row[1],
        "hnsw_bytes": row[2],
        "reloptions": row[3],
        "probe_sizes_returned_found": sizes,
    }


async def ensure_ann_reachable(
    owner_conn: AsyncConnection,
    target_ids: Sequence[uuid.UUID],
    probe_vector: Sequence[float],
    *,
    max_attempts: int = MAX_ATTEMPTS,
) -> int:
    """Return the number of probes it took (1 = reachable immediately)."""
    LAST_PROBE.update(targets=list(target_ids), vector=list(probe_vector))
    sizes: list[tuple[int, int]] = []
    for attempt in range(1, max_attempts + 1):
        ok, returned, found = await probe_reachability(
            owner_conn, target_ids, probe_vector
        )
        sizes.append((returned, found))
        if ok:
            return attempt
        if attempt < max_attempts:
            await _reindex()
    evidence = await _diagnostics(owner_conn, sizes)
    pytest.fail(
        f"ANN graph never became reachable: {len(list(target_ids))} target(s) "
        f"missing after {max_attempts} attempt(s) (REINDEX between attempts).\n"
        + json.dumps({"attempts": max_attempts, **evidence}, indent=2, default=str),
        pytrace=False,
    )
