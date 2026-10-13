"""ensure_index is cached per process (keyed by alias) behind an asyncio.Lock;
the cache resets on ES connection/not-found failures so recovery is automatic."""

import asyncio
import uuid
from typing import Any

import pytest
from elasticsearch import AsyncElasticsearch
from elasticsearch import ConnectionError as EsConnectionError
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.services import es_index, search_sync
from app.services.es_client import alias_name, get_es
from tests.conftest import MakeTenant
from tests.helpers.es_helpers import doc_index_state, es_ids, upload

CONTENT = "Cache content about warranty terms. "
INDICES_METHODS = ("exists_alias", "create", "update_aliases")


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch: pytest.MonkeyPatch):
    """A private alias per test and a cold cache before and after it."""
    monkeypatch.setattr(
        settings,
        "es_index_prefix",
        f"{settings.es_index_prefix}ec{uuid.uuid4().hex[:6]}-",
    )
    es_index.reset_ensure_cache()
    yield
    es_index.reset_ensure_cache()


def spy_on_indices(
    es: AsyncElasticsearch, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    calls: list[str] = []
    for name in INDICES_METHODS:
        real = getattr(es.indices, name)

        def make(real: Any, name: str) -> Any:
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                calls.append(name)
                return await real(*args, **kwargs)

            return wrapper

        monkeypatch.setattr(es.indices, name, make(real, name))
    return calls


async def test_second_call_makes_no_es_request(monkeypatch: pytest.MonkeyPatch) -> None:
    es = get_es()
    await es_index.ensure_index(es)
    calls = spy_on_indices(es, monkeypatch)
    await es_index.ensure_index(es)
    await es_index.ensure_index(es)
    assert calls == []


async def test_concurrent_first_calls_create_the_index_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = get_es()
    calls = spy_on_indices(es, monkeypatch)
    await asyncio.gather(*(es_index.ensure_index(es) for _ in range(8)))
    assert calls.count("create") == 1
    assert calls.count("update_aliases") == 1
    assert list(await es.indices.get_alias(name=alias_name())) == [
        es_index.index_name(1)
    ]


async def test_recovers_after_the_index_is_deleted(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    es = get_es()
    tenant = await make_tenant()
    first = await upload(client, tenant, "First", CONTENT + "one")
    assert (await doc_index_state(owner_conn, first))[
        "search_index_status"
    ] == "INDEXED"

    await es.indices.delete(index=es_index.index_name(1))  # alias vanishes with it
    second = await upload(client, tenant, "Second", CONTENT + "two")

    state = await doc_index_state(owner_conn, second)
    assert state["search_index_status"] == "INDEXED", state
    assert await es_ids(es, tenant_id=tenant["id"], document_id=second)
    # A plain index named like the alias would mean bulk auto-created one.
    assert list(await es.indices.get_alias(name=alias_name())) == [
        es_index.index_name(1)
    ]


async def test_connection_error_resets_the_cache(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = get_es()
    tenant = await make_tenant()
    doc = await upload(client, tenant, "Warm", CONTENT + "warm")
    await es_index.ensure_index(es)  # warm
    calls = spy_on_indices(es, monkeypatch)
    await es_index.ensure_index(es)
    assert calls == []

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise EsConnectionError("down")

    monkeypatch.setattr(search_sync, "async_bulk", boom)
    assert await search_sync.index_document(tenant["id"], doc, es) is False
    assert (await doc_index_state(owner_conn, doc))["search_index_status"] == "FAILED"

    monkeypatch.undo()  # real async_bulk again (spies and prefix too)
    monkeypatch.setattr(settings, "es_index_prefix", settings.es_index_prefix)
    calls = spy_on_indices(es, monkeypatch)
    await es_index.ensure_index(es)
    assert "exists_alias" in calls  # the cache was dropped, ES was asked again
