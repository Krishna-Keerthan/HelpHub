"""Hybrid search: branch-failure logging and the separate query-embedding timeout."""

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.deps import get_embedding_provider
from app.core.config import settings
from app.main import app
from app.services import es_client
from app.services.embeddings import FakeEmbeddingProvider
from app.services.es_client import get_es
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.helpers.es_helpers import upload

URL = "/search/hybrid"
TARGET = "quasar nebula zebra lantern orbit"
MARKER = "MARKER-7f3a-document-text"


async def _seed(client: AsyncClient, tenant: SeededTenant) -> None:
    await upload(client, tenant, "Target", TARGET)
    await get_es().indices.refresh(index=es_client.alias_name())


async def _post(client: AsyncClient, tenant: SeededTenant) -> Any:
    return await client.post(URL, json={"query": TARGET}, headers=auth_headers(tenant))


class _ExplodingProvider(FakeEmbeddingProvider):
    async def embed_query(self, text: str) -> list[float]:
        raise RuntimeError(f"backend echoed {MARKER}")


class _SlowProvider(FakeEmbeddingProvider):
    delay = 0.3

    async def embed_query(self, text: str) -> list[float]:
        await asyncio.sleep(self.delay)
        return await super().embed_query(text)


class _TooSlowProvider(_SlowProvider):
    delay = 0.8


async def test_branch_failure_log_has_tenant_branch_class_and_frames_but_no_message(
    client: AsyncClient, make_tenant: MakeTenant, caplog: pytest.LogCaptureFixture
) -> None:
    tenant = await make_tenant()
    await _seed(client, tenant)
    app.dependency_overrides[get_embedding_provider] = _ExplodingProvider

    with caplog.at_level("DEBUG"):
        response = await _post(client, tenant)

    assert response.json()["degraded"] == ["vector"]
    records = [r for r in caplog.records if "hybrid branch failed" in r.getMessage()]
    assert len(records) == 1
    line = records[0].getMessage()
    assert f"tenant={tenant['id']}" in line
    assert "branch=vector" in line
    assert "error=RuntimeError" in line
    assert "test_hybrid_failures.py:" in line  # traceback frame as file:line
    assert MARKER not in caplog.text
    assert records[0].exc_info is None


async def test_embedding_slower_than_the_branch_budget_but_under_its_own_succeeds(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    await _seed(client, tenant)
    monkeypatch.setattr(settings, "embedding_timeout_seconds", 0.5)
    monkeypatch.setattr(settings, "hybrid_branch_timeout_seconds", 0.2)
    app.dependency_overrides[get_embedding_provider] = _SlowProvider  # 0.3 s

    body = (await _post(client, tenant)).json()

    assert body["degraded"] == []
    assert any("vector" in h["found_by"] for h in body["results"])


async def test_embedding_over_its_limit_degrades_to_keyword_only(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    await _seed(client, tenant)
    monkeypatch.setattr(settings, "embedding_timeout_seconds", 0.5)
    monkeypatch.setattr(settings, "hybrid_branch_timeout_seconds", 0.2)
    app.dependency_overrides[get_embedding_provider] = _TooSlowProvider  # 0.8 s

    body = (await _post(client, tenant)).json()

    assert body["degraded"] == ["vector"]
    assert body["results"]
    assert all(h["found_by"] == ["keyword"] for h in body["results"])
