"""Postgres -> Elasticsearch sync: index_document, ingestion hook, failures."""

import logging
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.services import documents as documents_service
from app.services import es_client, search_sync
from app.services.embeddings import FakeEmbeddingProvider
from app.services.es_client import alias_name, get_es
from tests.conftest import MakeTenant
from tests.helpers.es_helpers import dead_client, doc_index_state, es_ids, upload
from tests.helpers.ingestion_helpers import idle_in_transaction, owner_chunks

CONTENT = "Sync test content about invoices. " * 5


async def test_ingestion_indexes_the_chunks_and_marks_indexed(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc_id = await upload(client, tenant, "Sync doc", CONTENT)
    chunk_ids = {str(r["id"]) for r in await owner_chunks(owner_conn, doc_id)}

    state = await doc_index_state(owner_conn, doc_id)
    assert state == {
        "status": "READY",
        "search_index_status": "INDEXED",
        "search_index_error": None,
    }
    assert (
        await es_ids(get_es(), tenant_id=tenant["id"], document_id=doc_id) == chunk_ids
    )
    stored = await get_es().get(index=alias_name(), id=next(iter(chunk_ids)))
    assert stored["_source"]["tenant_id"] == str(tenant["id"])
    assert stored["_source"]["title"] == "Sync doc"


async def test_document_read_exposes_the_index_status(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    from tests.conftest import auth_headers

    tenant = await make_tenant()
    doc_id = await upload(client, tenant, "Doc", CONTENT)
    response = await client.get(f"/documents/{doc_id}", headers=auth_headers(tenant))
    assert response.json()["search_index_status"] == "INDEXED"
    assert "search_index_error" not in response.json()


async def test_es_down_during_ingestion_leaves_the_document_ready(
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dead = dead_client()
    monkeypatch.setattr(es_client, "_client", dead)
    try:
        tenant = await make_tenant()
        doc_id = await upload(client, tenant, "Down doc", CONTENT)
    finally:
        await dead.close()
    state = await doc_index_state(owner_conn, doc_id)
    assert state["status"] == "READY"
    assert state["search_index_status"] == "FAILED"
    assert state["search_index_error"] == "ConnectionError"  # class name only


async def test_failure_then_success_clears_the_error(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc_id = await upload(client, tenant, "Retry doc", CONTENT)
    dead = dead_client()
    try:
        await search_sync.index_document(tenant["id"], doc_id, dead)
    finally:
        await dead.close()
    assert (await doc_index_state(owner_conn, doc_id))[
        "search_index_status"
    ] == "FAILED"

    await search_sync.index_document(tenant["id"], doc_id, get_es())

    assert await doc_index_state(owner_conn, doc_id) == {
        "status": "READY",
        "search_index_status": "INDEXED",
        "search_index_error": None,
    }


async def test_failure_logs_and_stores_only_the_class_name(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant = await make_tenant()
    doc_id = await upload(client, tenant, "Leak doc", "zq-private-text " * 20)
    caplog.set_level(logging.DEBUG)
    dead = dead_client()
    try:
        await search_sync.index_document(tenant["id"], doc_id, dead)
    finally:
        await dead.close()
    state = await doc_index_state(owner_conn, doc_id)
    everything = caplog.text + str(state)
    for leak in ("zq-private-text", "127.0.0.1", "Cannot connect", "Connection error"):
        assert leak not in everything


async def test_indexing_is_idempotent(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc_id = await upload(client, tenant, "Idem doc", CONTENT)
    before = await es_ids(get_es(), tenant_id=tenant["id"])
    await search_sync.index_document(tenant["id"], doc_id, get_es())
    await search_sync.index_document(tenant["id"], doc_id, get_es())
    assert await es_ids(get_es(), tenant_id=tenant["id"]) == before


async def test_bulk_runs_outside_any_transaction_and_before_indexed_is_recorded(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await make_tenant()
    doc_id = await upload(client, tenant, "Spy doc", CONTENT)
    # Reset so the next call is a fresh PENDING -> INDEXED transition.
    await owner_conn.execute(
        __import__("sqlalchemy").text(
            "UPDATE documents SET search_index_status='PENDING' WHERE id=:id"
        ),
        {"id": doc_id},
    )
    await owner_conn.commit()
    seen: list[tuple[int, str]] = []
    real_bulk = search_sync.async_bulk

    async def spy(*args, **kwargs):
        state = await doc_index_state(owner_conn, doc_id)
        seen.append(
            (await idle_in_transaction(owner_conn), state["search_index_status"])
        )
        return await real_bulk(*args, **kwargs)

    monkeypatch.setattr(search_sync, "async_bulk", spy)

    await search_sync.index_document(tenant["id"], doc_id, get_es())

    assert seen == [(0, "PENDING")]  # no open transaction; not yet INDEXED
    assert (await doc_index_state(owner_conn, doc_id))[
        "search_index_status"
    ] == "INDEXED"


async def test_partial_bulk_failures_mark_the_document_failed(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await make_tenant()
    doc_id = await upload(client, tenant, "Partial doc", CONTENT)

    async def one_failure(*args, **kwargs):
        return 2, 1  # (success, failed) as returned with stats_only=True

    monkeypatch.setattr(search_sync, "async_bulk", one_failure)
    await search_sync.index_document(tenant["id"], doc_id, get_es())

    state = await doc_index_state(owner_conn, doc_id)
    assert state["status"] == "READY"
    assert state["search_index_status"] == "FAILED"
    assert state["search_index_error"] == "BulkIndexError"


async def test_unknown_document_is_a_no_op(make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    await search_sync.index_document(tenant["id"], uuid.uuid4(), get_es())


async def test_other_tenants_cannot_be_indexed_through_a_foreign_id(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    doc_b = await upload(client, b, "B doc", CONTENT)
    await search_sync.index_document(a["id"], doc_b, get_es())
    assert await es_ids(get_es(), tenant_id=a["id"]) == set()


async def test_direct_ingest_uses_the_shared_client_by_default(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Direct", CONTENT
    )
    await documents_service.ingest_document(
        tenant["id"], doc.id, FakeEmbeddingProvider()
    )
    assert (await doc_index_state(owner_conn, doc.id))[
        "search_index_status"
    ] == "INDEXED"
    assert settings.es_alias  # sanity
