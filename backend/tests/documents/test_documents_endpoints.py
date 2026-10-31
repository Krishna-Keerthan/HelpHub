"""Documents API completion: JSON-only create, detail, chunks, delete."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

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


# --- GET /documents/{id} -----------------------------------------------------


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
