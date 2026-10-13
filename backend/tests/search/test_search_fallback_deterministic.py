"""Deterministic twin of tests/isolation/test_search_dead_tuples.py.

The ANN stage is replaced, so the fallback contract is checked without relying
on HNSW graph state: fewer hits than the tenant has chunks -> exact search
(used_fallback True, k hits); a healthy ANN stage -> used_fallback False.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.repositories import chunks as chunks_repo
from app.db.tenant_context import set_tenant
from app.services.search import search_in_session
from tests.conftest import (
    SeededTenant,
    insert_chunk,
    insert_document,
    unit_vector,
)

K = 3


async def _seed_chunks(
    owner_conn: AsyncConnection, tenant: SeededTenant, count: int
) -> set[uuid.UUID]:
    doc = await insert_document(owner_conn, tenant["id"], created_by=tenant["user_id"])
    ids = {
        await insert_chunk(
            owner_conn,
            tenant["id"],
            doc,
            chunk_index=i,
            embedding=unit_vector(1.0, 0.1 * (i + 1)),
        )
        for i in range(count)
    }
    await owner_conn.commit()
    return ids


@pytest.mark.parametrize("ann_hits", [0, 1, 2])
async def test_short_ann_stage_triggers_exact_fallback(
    ann_hits: int,
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    a_ids = await _seed_chunks(owner_conn, ta, K + 2)
    calls: list[int] = []

    async def short_ann(session, tenant_id, embedding, k):  # type: ignore[no-untyped-def]
        calls.append(k)
        return (await chunks_repo.exact_search(session, tenant_id, embedding, k))[
            :ann_hits
        ]

    monkeypatch.setattr(chunks_repo, "vector_search", short_ann)
    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, ta["id"])
        result = await search_in_session(session, ta["id"], unit_vector(1.0), K)

    assert calls == [K]
    assert result.used_fallback is True
    assert len(result.hits) == K
    assert {hit.chunk_id for hit in result.hits} <= a_ids
    scores = [hit.score for hit in result.hits]
    assert scores == sorted(scores, reverse=True)


async def test_healthy_ann_stage_does_not_fall_back(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    a_ids = await _seed_chunks(owner_conn, ta, K + 2)
    exact_calls: list[int] = []
    real_exact = chunks_repo.exact_search

    async def healthy_ann(session, tenant_id, embedding, k):  # type: ignore[no-untyped-def]
        return await real_exact(session, tenant_id, embedding, k)

    async def spy_exact(session, tenant_id, embedding, k):  # type: ignore[no-untyped-def]
        exact_calls.append(k)
        return await real_exact(session, tenant_id, embedding, k)

    monkeypatch.setattr(chunks_repo, "vector_search", healthy_ann)
    monkeypatch.setattr(chunks_repo, "exact_search", spy_exact)
    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, ta["id"])
        result = await search_in_session(session, ta["id"], unit_vector(1.0), K)

    assert result.used_fallback is False
    assert exact_calls == []  # the exact path really was not taken
    assert len(result.hits) == K
    assert {hit.chunk_id for hit in result.hits} <= a_ids
