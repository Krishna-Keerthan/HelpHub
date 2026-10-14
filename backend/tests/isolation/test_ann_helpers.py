"""ensure_ann_reachable: immediate success, and diagnostics at the bound."""

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import (
    SeededTenant,
    insert_chunk,
    insert_document,
    unit_vector,
)
from tests.isolation.ann_helpers import ensure_ann_reachable, probe_reachability


async def _seed_two(
    owner_conn: AsyncConnection, tenant: SeededTenant
) -> list[uuid.UUID]:
    doc = await insert_document(owner_conn, tenant["id"], created_by=tenant["user_id"])
    ids = [
        await insert_chunk(
            owner_conn,
            tenant["id"],
            doc,
            chunk_index=i,
            embedding=unit_vector(1.0, 0.1 * (i + 1)),
        )
        for i in range(2)
    ]
    await owner_conn.commit()
    return ids


async def test_returns_immediately_when_reachable(
    owner_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    ids = await _seed_two(owner_conn, two_tenants_seeded["tenant_a"])

    assert await ensure_ann_reachable(owner_conn, ids, unit_vector(1.0)) == 1


async def test_probe_reports_missing_targets(
    owner_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    ids = await _seed_two(owner_conn, two_tenants_seeded["tenant_a"])

    ok, returned, found = await probe_reachability(
        owner_conn, [*ids, uuid.uuid4()], unit_vector(1.0)
    )

    assert (ok, found) == (False, 2)
    assert returned >= 2


async def test_failure_at_the_bound_carries_diagnostics(
    owner_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    ids = await _seed_two(owner_conn, two_tenants_seeded["tenant_a"])

    with pytest.raises(pytest.fail.Exception) as raised:
        await ensure_ann_reachable(
            owner_conn, [*ids, uuid.uuid4()], unit_vector(1.0), max_attempts=1
        )

    message = str(raised.value)
    assert "after 1 attempt" in message
    evidence = json.loads(message[message.index("{") :])
    assert evidence["attempts"] == 1
    assert evidence["pgvector"]
    assert evidence["n_live_tup"] is not None
    assert evidence["hnsw_bytes"] > 0
    assert "reloptions" in evidence
    assert len(evidence["probe_sizes_returned_found"]) == 1
    assert evidence["probe_sizes_returned_found"][0][1] == 2
