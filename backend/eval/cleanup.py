"""Remove leftovers of earlier evaluation runs.

Usage (from backend/):  uv run python -m eval.cleanup

Holds the shared database lock. Deletes tenants whose slug starts with ``eval-``
(cascade) and Elasticsearch indices ``eval-*`` older than 10 minutes. Uses the
runtime role; never touches anything outside the eval- namespace.
"""

import asyncio
import sys
import time
import uuid
from collections.abc import Mapping, Sequence

from elasticsearch import AsyncElasticsearch
from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.services.es_client import get_es
from eval.guard import EVAL_PREFIX
from eval.lock import LockHeld, hold_lock

MIN_AGE_SECONDS = 600


def select_stale_indices(
    created_ms: Mapping[str, int], now_ms: int, min_age_s: int = MIN_AGE_SECONDS
) -> list[str]:
    return sorted(
        name
        for name, created in created_ms.items()
        if name.startswith(EVAL_PREFIX) and now_ms - created >= min_age_s * 1000
    )


def select_eval_tenants(rows: Sequence[tuple[uuid.UUID, str]]) -> list[uuid.UUID]:
    return [tenant_id for tenant_id, slug in rows if slug.startswith(EVAL_PREFIX)]


async def eval_tenants() -> list[tuple[uuid.UUID, str]]:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            text("SELECT id, slug FROM tenants WHERE slug LIKE 'eval-%'")
        )
        return [(row[0], row[1]) for row in rows]


async def delete_tenant(tenant_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
        )
        await session.commit()


async def eval_index_ages(es: AsyncElasticsearch) -> dict[str, int]:
    found = await es.indices.get_settings(
        index=f"{EVAL_PREFIX}*", ignore_unavailable=True, allow_no_indices=True
    )
    return {
        name: int(body["settings"]["index"]["creation_date"])
        for name, body in found.items()
    }


async def cleanup(
    es: AsyncElasticsearch, min_age_s: int = MIN_AGE_SECONDS
) -> tuple[int, int]:
    """Returns (tenants removed, indices removed). Caller holds the lock."""
    tenants = select_eval_tenants(await eval_tenants())
    for tenant_id in tenants:
        await delete_tenant(tenant_id)
    stale = select_stale_indices(
        await eval_index_ages(es), int(time.time() * 1000), min_age_s
    )
    if stale:
        await es.indices.delete(index=stale, ignore_unavailable=True)
    return len(tenants), len(stale)


async def _main() -> int:
    es = get_es()
    try:
        tenants, indices = await cleanup(es)
    finally:
        await es.close()
    print(f"removed tenants: {tenants}  indices: {indices}")
    return 0


def main() -> int:
    try:
        with hold_lock():
            return asyncio.run(_main())
    except LockHeld as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
