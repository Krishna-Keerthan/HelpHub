"""A versioned rebuild must not change documents.search_index_status of live
documents until the alias swap succeeds; on any failure statuses stay as they
were. After a successful swap, indexed documents are INDEXED."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.services import es_index, reindex
from app.services.es_client import alias_name, get_es
from tests.conftest import MakeTenant
from tests.helpers.es_helpers import doc_index_state, upload

CONTENT = "Status content about invoices. "


@pytest.fixture(autouse=True)
def private_alias(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        settings,
        "es_index_prefix",
        f"{settings.es_index_prefix}rs{uuid.uuid4().hex[:6]}-",
    )
    es_index.reset_ensure_cache()
    yield
    es_index.reset_ensure_cache()


async def set_status(
    owner_conn: AsyncConnection, doc_id: uuid.UUID, status: str
) -> None:
    await owner_conn.execute(
        text("UPDATE documents SET search_index_status = :s WHERE id = :id"),
        {"s": status, "id": doc_id},
    )
    await owner_conn.commit()


async def test_statuses_untouched_until_the_swap_then_indexed(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = get_es()
    tenant = await make_tenant()
    doc = await upload(client, tenant, "Live", CONTENT + "live")
    await set_status(owner_conn, doc, "PENDING")  # distinguishable from INDEXED

    seen: dict[str, Any] = {}
    real_update = es.indices.update_aliases

    async def spy_update(*args: Any, **kwargs: Any) -> Any:
        seen["status_at_swap"] = (await doc_index_state(owner_conn, doc))[
            "search_index_status"
        ]
        return await real_update(*args, **kwargs)

    monkeypatch.setattr(es.indices, "update_aliases", spy_update)
    summary = await reindex.reindex_all(es, tenant_ids=[tenant["id"]])

    assert summary.indexed == 1
    assert seen["status_at_swap"] == "PENDING"  # the new index is fully built by now
    assert (await doc_index_state(owner_conn, doc))["search_index_status"] == "INDEXED"


async def test_failed_swap_leaves_statuses_untouched(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = get_es()
    tenant = await make_tenant()
    doc = await upload(client, tenant, "Live", CONTENT + "swapfail")
    await set_status(owner_conn, doc, "PENDING")

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("forced swap failure")

    monkeypatch.setattr(es.indices, "update_aliases", boom)
    with pytest.raises(RuntimeError):
        await reindex.reindex_all(es, tenant_ids=[tenant["id"]])

    assert (await doc_index_state(owner_conn, doc))["search_index_status"] == "PENDING"
    assert not await es.indices.exists(index=es_index.index_name(2))
    assert list(await es.indices.get_alias(name=alias_name())) == [
        es_index.index_name(1)
    ]


async def test_incomplete_rebuild_leaves_statuses_untouched(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = get_es()
    tenant = await make_tenant()
    good = await upload(client, tenant, "Good", CONTENT + "good")
    bad = await upload(client, tenant, "Bad", CONTENT + "bad")
    await set_status(owner_conn, good, "PENDING")
    await set_status(owner_conn, bad, "INDEXED")
    real = reindex.search_sync.index_document

    async def fail_bad(
        tenant_id: uuid.UUID, document_id: uuid.UUID, es_: Any, **kw: Any
    ) -> bool:
        if document_id == bad:
            return False
        return await real(tenant_id, document_id, es_, **kw)

    monkeypatch.setattr(reindex.search_sync, "index_document", fail_bad)
    with pytest.raises(reindex.ReindexIncompleteError):
        await reindex.reindex_all(es, tenant_ids=[tenant["id"]])

    assert (await doc_index_state(owner_conn, good))["search_index_status"] == "PENDING"
    assert (await doc_index_state(owner_conn, bad))["search_index_status"] == "INDEXED"


async def test_allow_partial_records_failed_only_after_the_swap(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = get_es()
    tenant = await make_tenant()
    good = await upload(client, tenant, "Good", CONTENT + "good2")
    bad = await upload(client, tenant, "Bad", CONTENT + "bad2")
    real = reindex.search_sync.index_document

    async def fail_bad(
        tenant_id: uuid.UUID, document_id: uuid.UUID, es_: Any, **kw: Any
    ) -> bool:
        if document_id == bad:
            return False
        return await real(tenant_id, document_id, es_, **kw)

    monkeypatch.setattr(reindex.search_sync, "index_document", fail_bad)
    summary = await reindex.reindex_all(
        es, tenant_ids=[tenant["id"]], allow_partial=True
    )

    assert (summary.indexed, summary.failed) == (1, 1)
    assert (await doc_index_state(owner_conn, good))["search_index_status"] == "INDEXED"
    assert (await doc_index_state(owner_conn, bad))["search_index_status"] == "FAILED"
