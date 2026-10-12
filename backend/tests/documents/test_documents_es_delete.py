"""Deleting a document also deletes its ES chunks, scoped by tenant AND document."""

import logging
import uuid

import pytest
from httpx import AsyncClient

from app.services import es_client
from app.services.es_client import alias_name, get_es
from tests.conftest import MakeTenant, auth_headers
from tests.helpers.es_helpers import dead_client, es_ids, index_raw, upload

CONTENT = "Delete sync content about refunds. " * 5


async def test_delete_removes_only_that_documents_chunks(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    keep = await upload(client, tenant, "Keep", CONTENT + "keep")
    gone = await upload(client, tenant, "Gone", CONTENT + "gone")
    assert await es_ids(get_es(), tenant_id=tenant["id"], document_id=gone)

    response = await client.delete(f"/documents/{gone}", headers=auth_headers(tenant))

    assert response.status_code == 204
    assert await es_ids(get_es(), tenant_id=tenant["id"], document_id=gone) == set()
    assert await es_ids(get_es(), tenant_id=tenant["id"], document_id=keep)


async def test_delete_is_scoped_by_tenant_even_for_the_same_document_id(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    """An ES entry that claims another tenant but carries this document id
    must survive: delete_by_query filters on tenant_id AND document_id."""
    a, b = await make_tenant(), await make_tenant()
    doc_a = await upload(client, a, "A doc", CONTENT)
    foreign = uuid.uuid4()
    await index_raw(
        get_es(),
        chunk_id=foreign,
        tenant_id=b["id"],
        document_id=doc_a,  # same document id, other tenant
        content="b side entry",
    )

    await client.delete(f"/documents/{doc_a}", headers=auth_headers(a))

    assert await es_ids(get_es(), tenant_id=b["id"]) == {str(foreign)}


async def test_delete_by_query_body_names_tenant_and_document(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    doc = await upload(client, tenant, "Doc", CONTENT)
    es = get_es()
    sent: list[dict] = []
    real = es.delete_by_query

    async def spy(**kwargs):
        sent.append(kwargs)
        return await real(**kwargs)

    monkeypatch.setattr(es, "delete_by_query", spy)

    await client.delete(f"/documents/{doc}", headers=auth_headers(tenant))

    (call,) = sent
    assert call["index"] == alias_name()
    assert call["conflicts"] == "proceed"
    filters = call["query"]["bool"]["filter"]
    assert {"term": {"tenant_id": str(tenant["id"])}} in filters
    assert {"term": {"document_id": str(doc)}} in filters


async def test_es_failure_never_fails_the_delete_and_logs_only_the_class(
    client: AsyncClient,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant = await make_tenant()
    doc = await upload(client, tenant, "Doc", CONTENT)
    dead = dead_client()
    monkeypatch.setattr(es_client, "_client", dead)
    caplog.set_level(logging.DEBUG)
    try:
        response = await client.delete(
            f"/documents/{doc}", headers=auth_headers(tenant)
        )
    finally:
        await dead.close()

    assert response.status_code == 204
    assert "ConnectionError" in caplog.text
    for leak in ("127.0.0.1", "Cannot connect"):
        assert leak not in caplog.text
    monkeypatch.undo()
    get = await client.get(f"/documents/{doc}", headers=auth_headers(tenant))
    assert get.status_code == 404  # the database delete did happen
