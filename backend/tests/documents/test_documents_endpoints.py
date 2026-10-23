"""Documents API completion: JSON-only create, detail, chunks, delete."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import documents as documents_service
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.helpers.ingestion_helpers import CONTENT, owner_chunks, owner_document

Tenants = dict[str, SeededTenant]


async def _create(client: AsyncClient, tenant: SeededTenant, content: str = CONTENT):
    response = await client.post(
        "/documents",
        json={"title": "Doc", "content": content},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- POST /documents is JSON only --------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "content": b'{"title": "t", "content": "c"}',
            "headers": {"Content-Type": "text/plain"},
        },
        {"files": {"file": ("a.txt", b"text", "text/plain")}},
        {"data": {"title": "t", "content": "c"}},  # form-urlencoded
        {"content": b"raw text"},  # no Content-Type at all
    ],
    ids=["text-plain", "multipart", "form-urlencoded", "no-content-type"],
)
async def test_post_documents_non_json_is_415(
    client: AsyncClient, make_tenant: MakeTenant, kwargs: dict
) -> None:
    tenant = await make_tenant()
    headers = {**auth_headers(tenant), **kwargs.pop("headers", {})}
    response = await client.post("/documents", headers=headers, **kwargs)
    assert response.status_code == 415


async def test_post_documents_json_with_charset_is_accepted(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await client.post(
        "/documents",
        content=b'{"title": "t", "content": "Charset is fine."}',
        headers={
            **auth_headers(tenant),
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    assert response.status_code == 201


async def test_post_documents_malformed_json_is_422(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await client.post(
        "/documents",
        content=b"{not json",
        headers={**auth_headers(tenant), "Content-Type": "application/json"},
    )
    assert response.status_code == 422


async def test_document_vanishing_mid_flight_is_409(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()

    async def vanished(*args, **kwargs):
        raise documents_service.DocumentNotFound("document disappeared")

    monkeypatch.setattr(documents_service, "ingest_document", vanished)
    response = await client.post(
        "/documents",
        json={"title": "Doc", "content": CONTENT},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 409
    assert "disappeared" not in response.text


# --- GET /documents/{id} -----------------------------------------------------


async def test_get_document_detail(
    client: AsyncClient, two_tenants_seeded: Tenants
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_id = await _create(client, ta)

    own = await client.get(f"/documents/{doc_id}", headers=auth_headers(ta))
    assert own.status_code == 200
    assert own.json()["id"] == doc_id
    assert own.json()["status"] == "READY"
    assert "raw_text" not in own.json()

    assert (
        await client.get(f"/documents/{doc_id}", headers=auth_headers(tb))
    ).status_code == 404


@pytest.mark.parametrize("path", ["/documents/not-a-uuid"])
async def test_non_uuid_path_is_422(
    client: AsyncClient, make_tenant: MakeTenant, path: str
) -> None:
    tenant = await make_tenant()
    assert (await client.get(path, headers=auth_headers(tenant))).status_code == 422


async def test_delete_non_uuid_path_is_422(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()  # admin
    response = await client.delete(
        "/documents/not-a-uuid", headers=auth_headers(tenant)
    )
    assert response.status_code == 422


# --- DELETE /documents/{id} --------------------------------------------------


async def test_admin_delete_cascades_chunks(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    admin = await make_tenant(role="admin")
    doc_id = await _create(client, admin)
    assert await owner_chunks(owner_conn, doc_id)

    response = await client.delete(f"/documents/{doc_id}", headers=auth_headers(admin))

    assert response.status_code == 204
    assert response.content == b""
    assert await owner_document(owner_conn, doc_id) is None
    assert await owner_chunks(owner_conn, doc_id) == []
    missing = await client.delete(f"/documents/{doc_id}", headers=auth_headers(admin))
    assert missing.status_code == 404


async def test_agent_can_upload_but_not_delete(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    agent = await make_tenant(role="agent")
    doc_id = await _create(client, agent)

    response = await client.delete(f"/documents/{doc_id}", headers=auth_headers(agent))

    assert response.status_code == 403
    assert await owner_document(owner_conn, doc_id) is not None


async def test_deleted_document_never_appears_in_search(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    admin = await make_tenant(role="admin")
    headers = auth_headers(admin)
    doc_id = await _create(client, admin, "Billing refunds are processed weekly.")
    query = {"query": "billing refunds", "k": 50}

    before = await client.post("/search", json=query, headers=headers)
    assert doc_id in {hit["document_id"] for hit in before.json()}

    assert (
        await client.delete(f"/documents/{doc_id}", headers=headers)
    ).status_code == 204
    after = await client.post("/search", json=query, headers=headers)
    assert after.status_code == 200
    assert doc_id not in {hit["document_id"] for hit in after.json()}


async def test_unknown_document_delete_is_404(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    admin = await make_tenant(role="admin")
    response = await client.delete(
        f"/documents/{uuid.uuid4()}", headers=auth_headers(admin)
    )
    assert response.status_code == 404
