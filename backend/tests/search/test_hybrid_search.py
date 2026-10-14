"""Hybrid search (BM25 + vector, RRF): fusion, branch independence, degradation."""

import asyncio
import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_embedding_provider
from app.core.config import settings
from app.db import tenant_context
from app.db.repositories import chunks as chunks_repo
from app.main import app
from app.services import es_client, hybrid_search
from app.services.embeddings import FakeEmbeddingProvider
from app.services.es_client import get_es
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.helpers.es_helpers import dead_client, upload
from tests.helpers.ingestion_helpers import (
    QuerySpyProvider,
    idle_in_transaction,
)

URL = "/search/hybrid"
HIT_FIELDS = {
    "chunk_id", "document_id", "document_title", "chunk_index", "content",
    "char_start", "char_end", "rrf_score", "found_by", "vector_score",
    "keyword_score",
}  # fmt: skip

# The fake embedder maps equal text to equal vectors, so querying with a chunk's
# exact text makes that chunk the vector rank 1; its words also make it BM25 rank 1.
TARGET = "quasar nebula zebra lantern orbit"


async def _refresh() -> None:
    await get_es().indices.refresh(index=es_client.alias_name())


async def _post(client: AsyncClient, tenant: SeededTenant, body: dict[str, Any]) -> Any:
    return await client.post(URL, json=body, headers=auth_headers(tenant))


async def _seed_fusion_corpus(client: AsyncClient, tenant: SeededTenant) -> uuid.UUID:
    target = await upload(client, tenant, "Target", TARGET)
    # keyword-friendly but far from the query vector
    await upload(client, tenant, "Keyword only", f"{TARGET} plus many extra words here")
    for i in range(8):
        await upload(client, tenant, f"Noise {i}", f"unrelated filler paragraph {i}")
    await _refresh()
    return target


# --- fusion ----------------------------------------------------------------------


async def test_chunk_found_by_both_outranks_single_source_chunks(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    target_doc = await _seed_fusion_corpus(client, tenant)
    monkeypatch.setattr(settings, "hybrid_candidates", 2)

    response = await _post(client, tenant, {"query": TARGET, "k": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] == []
    hits = body["results"]
    first = hits[0]
    assert first["document_id"] == str(target_doc)
    assert first["found_by"] == ["vector", "keyword"]
    assert first["vector_score"] == pytest.approx(1.0, abs=1e-4)
    assert first["keyword_score"] > 0
    assert all(first["rrf_score"] > h["rrf_score"] for h in hits[1:])
    assert any(len(h["found_by"]) == 1 for h in hits[1:])  # single-source exists
    for hit in hits:
        assert set(hit) == HIT_FIELDS
    ids = [h["chunk_id"] for h in hits]
    assert len(ids) == len(set(ids))  # deduplicated


async def test_scores_follow_rrf_with_the_configured_k(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)

    hits = (await _post(client, tenant, {"query": TARGET, "k": 5})).json()["results"]

    assert settings.rrf_k == 60
    assert hits[0]["rrf_score"] == pytest.approx(2 / 61)  # rank 1 in both lists
    scores = [h["rrf_score"] for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(0 < s <= 2 / 61 for s in scores)


async def test_response_never_exposes_internal_fields(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)

    response = await _post(client, tenant, {"query": TARGET})

    assert set(response.json()) == {"results", "degraded"}
    for forbidden in ("used_fallback", "vector_fallback", "embedding", "raw_text"):
        assert forbidden not in response.text


# --- validation, auth, clamps --------------------------------------------------


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.post(URL, json={"query": "x"})).status_code == 401
    bad = await client.post(
        URL, json={"query": "x"}, headers={"Authorization": "Bearer nonsense"}
    )
    assert bad.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 1001},
        {"query": "ok", "k": 0},
        {"query": "ok", "k": 51},
        {"k": 3},
        {"query": "ok", "unknown": 1},
    ],
    ids=repr,
)
async def test_invalid_bodies_are_422(
    client: AsyncClient, make_tenant: MakeTenant, body: dict
) -> None:
    tenant = await make_tenant()
    assert (await _post(client, tenant, body)).status_code == 422


async def test_query_is_stripped_and_k_defaults_to_5(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    for i in range(7):
        await upload(client, tenant, f"Doc {i}", f"shared words document {i}")
    await _refresh()

    response = await _post(client, tenant, {"query": "  shared words  "})

    assert response.status_code == 200
    assert len(response.json()["results"]) == 5


async def test_service_clamps_k_and_candidates(
    make_tenant: MakeTenant,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await make_tenant()
    for i in range(3):
        await upload(client, tenant, f"Doc {i}", f"clamp check words {i}")
    await _refresh()
    seen: dict[str, int] = {}
    real = hybrid_search.search_in_session

    async def spy(session: Any, tenant_id: Any, embedding: Any, k: int) -> Any:
        seen["candidates"] = k
        return await real(session, tenant_id, embedding, k)

    monkeypatch.setattr(hybrid_search, "search_in_session", spy)
    monkeypatch.setattr(settings, "hybrid_candidates", 10_000)
    provider = FakeEmbeddingProvider()

    low = await hybrid_search.hybrid_search(
        tenant["id"], "clamp check words", 0, provider, get_es()
    )
    high = await hybrid_search.hybrid_search(
        tenant["id"], "clamp check words", 999, provider, get_es()
    )

    assert len(low.hits) == 1  # k=0 -> 1
    assert len(high.hits) == 3  # k=999 -> 50, only 3 chunks exist
    assert seen["candidates"] == chunks_repo.MAX_K  # 10_000 -> 50


# --- branch independence ---------------------------------------------------------


async def test_branches_use_distinct_sessions(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)
    created: list[int] = []
    used: dict[str, int] = {}
    real_factory = tenant_context.AsyncSessionLocal

    def factory() -> Any:
        session = real_factory()
        created.append(id(session))
        return session

    real_vector, real_hydrate = chunks_repo.vector_search, chunks_repo.hydrate_chunks

    async def vector_spy(session: Any, *args: Any) -> Any:
        used["vector"] = id(session)
        return await real_vector(session, *args)

    async def hydrate_spy(session: Any, *args: Any) -> Any:
        used["hydrate"] = id(session)
        return await real_hydrate(session, *args)

    monkeypatch.setattr(tenant_context, "AsyncSessionLocal", factory)
    monkeypatch.setattr(chunks_repo, "vector_search", vector_spy)
    monkeypatch.setattr(chunks_repo, "hydrate_chunks", hydrate_spy)

    result = await hybrid_search.hybrid_search(
        tenant["id"], TARGET, 5, FakeEmbeddingProvider(), get_es()
    )

    assert result.degraded == []
    assert used["vector"] != used["hydrate"]
    assert len(created) == 2 and len(set(created)) == 2  # one short session per branch


async def test_no_transaction_open_during_the_es_call(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)
    seen: list[int] = []
    real = get_es()

    class SpyEs:
        async def search(self, **kwargs: Any) -> Any:
            await asyncio.sleep(0.5)  # the vector branch has finished by now
            seen.append(await idle_in_transaction(owner_conn))
            return await real.search(**kwargs)

    app.dependency_overrides[get_es] = lambda: SpyEs()
    try:
        response = await _post(client, tenant, {"query": TARGET})
    finally:
        app.dependency_overrides.pop(get_es, None)

    assert response.status_code == 200
    assert response.json()["degraded"] == []
    assert seen == [0]


async def test_no_transaction_open_while_embedding(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)
    seen: list[int] = []
    real = get_es()

    class SlowEs:  # keeps the keyword branch inside the ES call (no transaction)
        async def search(self, **kwargs: Any) -> Any:
            await asyncio.sleep(0.5)
            return await real.search(**kwargs)

    async def check() -> None:
        seen.append(await idle_in_transaction(owner_conn))

    spy = QuerySpyProvider(check)
    app.dependency_overrides[get_es] = lambda: SlowEs()
    app.dependency_overrides[get_embedding_provider] = lambda: spy
    try:
        response = await _post(client, tenant, {"query": TARGET})
    finally:
        app.dependency_overrides.pop(get_es, None)

    assert response.status_code == 200
    assert spy.query_calls == 1
    assert seen == [0]


# --- degradation matrix ----------------------------------------------------------


class _FailingProvider(FakeEmbeddingProvider):
    async def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("embedding backend exploded: SECRET-DETAIL")


async def test_es_down_degrades_to_vector_only(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)
    app.dependency_overrides[get_es] = dead_client
    try:
        response = await _post(client, tenant, {"query": TARGET})
    finally:
        app.dependency_overrides.pop(get_es, None)

    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] == ["keyword"]
    assert body["results"], "vector results are still returned"
    assert all(h["found_by"] == ["vector"] for h in body["results"])
    assert all(h["keyword_score"] is None for h in body["results"])
    assert body["results"][0]["rrf_score"] == pytest.approx(1 / 61)


async def test_embedding_failure_degrades_to_keyword_only(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)
    app.dependency_overrides[get_embedding_provider] = _FailingProvider

    response = await _post(client, tenant, {"query": TARGET})

    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] == ["vector"]
    assert body["results"]
    assert all(h["found_by"] == ["keyword"] for h in body["results"])
    assert all(h["vector_score"] is None for h in body["results"])
    assert "SECRET-DETAIL" not in response.text


async def test_vector_database_failure_degrades_to_keyword_only(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)

    async def boom(*args: Any) -> Any:
        raise ConnectionError("db went away")

    monkeypatch.setattr(chunks_repo, "vector_search", boom)

    body = (await _post(client, tenant, {"query": TARGET})).json()

    assert body["degraded"] == ["vector"]
    assert body["results"]


async def test_both_branches_down_is_a_generic_503(
    client: AsyncClient, make_tenant: MakeTenant, caplog: pytest.LogCaptureFixture
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)
    app.dependency_overrides[get_es] = dead_client
    app.dependency_overrides[get_embedding_provider] = _FailingProvider
    try:
        with caplog.at_level("DEBUG"):
            response = await _post(client, tenant, {"query": TARGET})
    finally:
        app.dependency_overrides.pop(get_es, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "search unavailable"}
    assert "SECRET-DETAIL" not in response.text
    assert TARGET not in caplog.text  # branch names and class names only
    assert "SECRET-DETAIL" not in caplog.text


async def test_slow_es_branch_times_out_and_the_request_returns_in_budget(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)
    monkeypatch.setattr(settings, "hybrid_branch_timeout_seconds", 0.5)

    class HangingEs:
        async def search(self, **kwargs: Any) -> Any:
            await asyncio.sleep(30)

    app.dependency_overrides[get_es] = lambda: HangingEs()
    started = time.monotonic()
    try:
        response = await _post(client, tenant, {"query": TARGET})
    finally:
        app.dependency_overrides.pop(get_es, None)
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.json()["degraded"] == ["keyword"]
    assert elapsed < 0.5 + 2.0, elapsed


# --- short ANN branch ------------------------------------------------------------


async def test_short_ann_branch_still_returns_the_tenants_chunks_via_fallback(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)

    async def short_ann(session: Any, tenant_id: Any, embedding: Any, k: int) -> list:
        return []  # the ANN stage "loses" the tenant's nodes (AR-15)

    monkeypatch.setattr(chunks_repo, "vector_search", short_ann)

    result = await hybrid_search.hybrid_search(
        tenant["id"], TARGET, 5, FakeEmbeddingProvider(), get_es()
    )

    assert result.vector_fallback is True
    assert result.degraded == []
    vector_hits = [h for h in result.hits if "vector" in h.found_by]
    assert vector_hits, "the exact fallback supplied the vector branch"
    assert result.hits[0].found_by == ["vector", "keyword"]


async def test_healthy_ann_does_not_report_fallback(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await _seed_fusion_corpus(client, tenant)

    result = await hybrid_search.hybrid_search(
        tenant["id"], TARGET, 5, FakeEmbeddingProvider(), get_es()
    )

    assert result.vector_fallback is False
