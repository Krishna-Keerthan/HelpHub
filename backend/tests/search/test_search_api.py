"""POST /search: validation, response shape, tenant titles, no open
transaction while the query is embedded."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_embedding_provider
from app.main import app
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.helpers.ingestion_helpers import (
    CONTENT,
    QuerySpyProvider,
    idle_in_transaction,
)

FIELDS = {
    "chunk_id",
    "document_id",
    "document_title",
    "chunk_index",
    "content",
    "char_start",
    "char_end",
    "score",
    "rrf_score",
    "found_by",
}


async def _upload(client: AsyncClient, tenant: SeededTenant, title: str, content: str):
    response = await client.post(
        "/documents",
        json={"title": title, "content": content},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize(
    "query", ["", "   \n\t ", "x" * 1001, " " + "y" * 1001], ids=repr
)
async def test_invalid_query_is_422(
    client: AsyncClient, make_tenant: MakeTenant, query: str
) -> None:
    tenant = await make_tenant()
    response = await client.post(
        "/search", json={"query": query}, headers=auth_headers(tenant)
    )
    assert response.status_code == 422


async def test_query_of_1000_chars_after_strip_is_accepted(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await client.post(
        "/search",
        json={"query": "  " + "z" * 1000 + "  "},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 200


async def test_search_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/search", json={"query": "anything"})
    assert response.status_code == 401


async def test_response_shape_and_offsets(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc_id = await _upload(client, tenant, "Offsets doc", CONTENT)

    response = await client.post(
        "/search", json={"query": "exact offsets"}, headers=auth_headers(tenant)
    )

    assert response.status_code == 200
    hits = response.json()
    assert 0 < len(hits) <= 5  # k defaults to 5
    for hit in hits:
        assert set(hit) == FIELDS
        assert hit["document_id"] == doc_id
        assert hit["document_title"] == "Offsets doc"
        assert CONTENT[hit["char_start"] : hit["char_end"]] == hit["content"]
    for forbidden in ("used_fallback", "embedding", "raw_text"):
        assert forbidden not in response.text


async def test_default_k_is_5(client: AsyncClient, make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    for i in range(7):
        await _upload(client, tenant, f"Doc {i}", f"Distinct document number {i}.")
    response = await client.post(
        "/search", json={"query": "document"}, headers=auth_headers(tenant)
    )
    assert response.status_code == 200
    assert len(response.json()) == 5


async def test_titles_come_from_own_tenant_only(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    await _upload(client, ta, "A title", "Shared words about resetting passwords.")
    await _upload(
        client, tb, "B secret title", "Shared words about resetting passwords."
    )

    response = await client.post(
        "/search",
        json={"query": "resetting passwords", "k": 50},
        headers=auth_headers(ta),
    )

    assert response.status_code == 200
    assert {hit["document_title"] for hit in response.json()} == {"A title"}
    assert "B secret title" not in response.text


async def test_no_transaction_open_while_embedding_query(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await _upload(client, tenant, "Doc", CONTENT)
    seen: list[int] = []

    async def check() -> None:
        seen.append(await idle_in_transaction(owner_conn))

    spy = QuerySpyProvider(check)
    app.dependency_overrides[get_embedding_provider] = lambda: spy

    response = await client.post(
        "/search", json={"query": "offsets"}, headers=auth_headers(tenant)
    )

    assert response.status_code == 200
    assert spy.query_calls == 1
    assert seen == [0]
