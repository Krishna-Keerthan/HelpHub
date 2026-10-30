import uuid

import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_document_api_error_codes(client, two_tenants_seeded):
    ta = two_tenants_seeded["tenant_a"]
    headers = auth_headers(ta)

    # 422 Unprocessable Entity (Empty body/fields)
    res_422 = await client.post("/documents", json={}, headers=headers)
    assert res_422.status_code == 422

    # 415 Unsupported Media Type
    res_415 = await client.post("/documents", content="raw text", headers=headers)
    assert res_415.status_code == 415

    # Same with an explicit non-JSON content type
    res_415_text = await client.post(
        "/documents",
        content="raw text",
        headers={**headers, "Content-Type": "text/plain"},
    )
    assert res_415_text.status_code == 415


@pytest.mark.asyncio
async def test_agent_cannot_delete_document_returns_403(
    client, two_tenants_seeded, make_document
):
    tb = two_tenants_seeded["tenant_b"]  # Role: agent
    doc_id = await make_document(tb)
    headers = auth_headers(tb)

    response = await client.delete(f"/documents/{doc_id}", headers=headers)
    assert response.status_code == 403

    # The document is still there.
    still_there = await client.get(f"/documents/{doc_id}", headers=headers)
    assert still_there.status_code == 200


@pytest.mark.asyncio
async def test_list_views_never_contain_raw_text(
    client, two_tenants_seeded, make_document
):
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]
    doc_a = await make_document(ta, raw_text="secret body of A")
    doc_b = await make_document(tb, raw_text="secret body of B")

    response = await client.get("/documents", headers=auth_headers(ta))
    assert response.status_code == 200
    docs = response.json()
    # Non-vacuous: A sees its own document and nothing of B's.
    assert {d["id"] for d in docs} == {str(doc_a)}
    assert str(doc_b) not in response.text
    for doc in docs:
        assert "raw_text" not in doc
    assert "secret body" not in response.text


@pytest.mark.asyncio
async def test_detail_view_never_contains_raw_text(
    client, two_tenants_seeded, make_document
):
    ta = two_tenants_seeded["tenant_a"]
    doc_a = await make_document(ta, raw_text="secret body of A")

    response = await client.get(f"/documents/{doc_a}", headers=auth_headers(ta))
    assert response.status_code == 200
    assert response.json()["id"] == str(doc_a)
    assert "raw_text" not in response.json()
    assert "secret body" not in response.text


@pytest.mark.asyncio
async def test_other_tenant_document_is_404(client, two_tenants_seeded, make_document):
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]
    doc_b = await make_document(tb)
    headers = auth_headers(ta)  # tenant A is admin

    assert (await client.get(f"/documents/{doc_b}", headers=headers)).status_code == 404
    delete = await client.delete(f"/documents/{doc_b}", headers=headers)
    assert delete.status_code == 404
    # B's document survived the attempted delete.
    own = await client.get(f"/documents/{doc_b}", headers=auth_headers(tb))
    assert own.status_code == 200


@pytest.mark.asyncio
async def test_unknown_document_is_404(client, two_tenants_seeded):
    ta = two_tenants_seeded["tenant_a"]
    response = await client.get(f"/documents/{uuid.uuid4()}", headers=auth_headers(ta))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_delete_own_document(client, two_tenants_seeded, make_document):
    ta = two_tenants_seeded["tenant_a"]  # admin
    doc_a = await make_document(ta)
    headers = auth_headers(ta)

    assert (
        await client.delete(f"/documents/{doc_a}", headers=headers)
    ).status_code == 204
    assert (await client.get(f"/documents/{doc_a}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_documents_require_authentication(client):
    assert (await client.get("/documents")).status_code == 401
    assert (await client.post("/documents", json={})).status_code == 401


async def _total(client, tenant, query: str = "") -> tuple[int, int]:
    response = await client.get(f"/documents{query}", headers=auth_headers(tenant))
    assert response.status_code == 200
    return len(response.json()), int(response.headers["X-Total-Count"])


@pytest.mark.asyncio
async def test_total_count_header_for_zero_one_and_many(
    client, make_tenant, make_document
):
    tenant = await make_tenant()
    assert await _total(client, tenant) == (0, 0)
    await make_document(tenant, raw_text="first")
    assert await _total(client, tenant) == (1, 1)
    for i in range(4):
        await make_document(tenant, raw_text=f"more {i}")
    assert await _total(client, tenant) == (5, 5)


@pytest.mark.asyncio
async def test_total_count_ignores_limit_and_offset(client, make_tenant, make_document):
    tenant = await make_tenant()
    for i in range(5):
        await make_document(tenant, raw_text=f"doc {i}")
    assert await _total(client, tenant, "?limit=2") == (2, 5)
    assert await _total(client, tenant, "?limit=2&offset=4") == (1, 5)
    assert await _total(client, tenant, "?limit=2&offset=50") == (0, 5)


@pytest.mark.asyncio
async def test_total_count_header_absent_on_errors(client, two_tenants_seeded):
    headers = auth_headers(two_tenants_seeded["tenant_a"])
    bad = await client.get("/documents?limit=0", headers=headers)
    assert bad.status_code == 422
    assert "X-Total-Count" not in bad.headers
    anonymous = await client.get("/documents")
    assert anonymous.status_code == 401
    assert "X-Total-Count" not in anonymous.headers
