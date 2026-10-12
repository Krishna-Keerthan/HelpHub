"""POST /search/keyword: validation, tenant from the JWT only, 503 when ES is down."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import es_client, keyword_search
from app.services.es_client import get_es
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.helpers.es_helpers import dead_client, upload
from tests.helpers.ingestion_helpers import idle_in_transaction

FIELDS = {
    "chunk_id", "document_id", "document_title", "chunk_index", "content",
    "char_start", "char_end", "score",
}  # fmt: skip
URL = "/search/keyword"


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (
        await client.post(URL, json={"query": "financial report"})
    ).status_code == 401
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
    ],
    ids=repr,
)
async def test_invalid_bodies_are_422(
    client: AsyncClient, make_tenant: MakeTenant, body: dict
) -> None:
    tenant = await make_tenant()
    response = await client.post(URL, json=body, headers=auth_headers(tenant))
    assert response.status_code == 422


async def test_body_tenant_id_is_rejected_and_no_search_runs(
    client: AsyncClient,
    two_tenants_seeded: dict[str, SeededTenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    await upload(client, tb, "B doc", "roadmap secrets of tenant b")
    calls: list[object] = []

    async def spy(*args, **kwargs):
        calls.append(args)
        return []

    monkeypatch.setattr(keyword_search, "search", spy)

    response = await client.post(
        URL,
        json={"query": "project roadmap", "tenant_id": str(tb["id"])},
        headers=auth_headers(ta),
    )

    assert response.status_code == 422
    assert calls == []
    assert "tenant b" not in response.text


async def test_results_have_the_search_shape_and_only_the_callers_tenant(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    text_a = "Refund policy for tenant A customers."
    await upload(client, ta, "A title", text_a)
    await upload(client, tb, "B secret title", "Refund policy for tenant B only.")
    await get_es().indices.refresh(index=es_client.alias_name())

    response = await client.post(
        URL, json={"query": "refund policy", "k": 50}, headers=auth_headers(ta)
    )

    assert response.status_code == 200
    hits = response.json()
    assert len(hits) == 1
    assert set(hits[0]) == FIELDS
    assert hits[0]["document_title"] == "A title"
    assert hits[0]["content"] == text_a
    assert hits[0]["score"] > 0
    assert "B secret title" not in response.text
    for forbidden in ("embedding", "raw_text", "_source"):
        assert forbidden not in response.text


async def test_default_k_is_5(client: AsyncClient, make_tenant: MakeTenant) -> None:
    tenant = await make_tenant()
    for i in range(7):
        await upload(client, tenant, f"Doc {i}", f"Shared widget text number {i}.")
    await get_es().indices.refresh(index=es_client.alias_name())
    response = await client.post(
        URL, json={"query": "widget"}, headers=auth_headers(tenant)
    )
    assert response.status_code == 200
    assert len(response.json()) == 5


async def test_es_down_is_503_with_a_generic_body(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()
    dead = dead_client()
    monkeypatch.setattr(es_client, "_client", dead)
    try:
        response = await client.post(
            URL, json={"query": "secret words"}, headers=auth_headers(tenant)
        )
    finally:
        await dead.close()
    assert response.status_code == 503
    assert response.json() == {"detail": "search unavailable"}
    for leak in ("127.0.0.1", "Connection", "secret words"):
        assert leak not in response.text


async def test_no_transaction_is_open_during_the_es_call(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await upload(client, tenant, "Doc", "spy text about invoices")
    es = get_es()
    seen: list[int] = []
    real = es.search

    async def spy(**kwargs):
        seen.append(await idle_in_transaction(owner_conn))
        return await real(**kwargs)

    es.search = spy  # type: ignore[method-assign]
    try:
        response = await client.post(
            URL, json={"query": "invoices"}, headers=auth_headers(tenant)
        )
    finally:
        del es.search
    assert response.status_code == 200
    assert seen == [0]
