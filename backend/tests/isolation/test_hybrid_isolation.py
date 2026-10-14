"""Hybrid search never crosses tenants, whichever branch is attacked."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.services import es_client, hybrid_search
from app.services.es_client import get_es
from tests.conftest import SeededTenant, auth_headers
from tests.helpers.es_helpers import index_raw, upload, upload_and_index
from tests.helpers.ingestion_helpers import owner_chunks

URL = "/search/hybrid"
SHARED = "quasar nebula zebra lantern orbit"
# gate-allow: secret fake value used only by this test
SECRET = "zq-hybrid-secret-of-tenant-b"


async def _chunk_ids(owner_conn: AsyncConnection, doc_id: Any) -> set[str]:
    return {str(row["id"]) for row in await owner_chunks(owner_conn, doc_id)}


async def test_same_text_in_both_tenants_returns_only_the_callers_chunks(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_a = await upload(client, ta, "A title", SHARED)
    doc_b = await upload(client, tb, "B secret title", SHARED)
    await get_es().indices.refresh(index=es_client.alias_name())
    ids_a, ids_b = (
        await _chunk_ids(owner_conn, doc_a),
        await _chunk_ids(owner_conn, doc_b),
    )

    response = await client.post(
        URL, json={"query": SHARED, "k": 50}, headers=auth_headers(ta)
    )

    assert response.status_code == 200
    hits = response.json()["results"]
    assert {h["chunk_id"] for h in hits} == ids_a
    assert not {h["chunk_id"] for h in hits} & ids_b
    assert {h["document_title"] for h in hits} == {"A title"}
    assert "B secret title" not in response.text


async def test_poisoned_es_entry_is_dropped_next_to_the_real_vector_branch(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    es = get_es()
    await upload(client, ta, "A doc", "tenant a ordinary content about invoices")
    doc_b, rows_b = await upload_and_index(
        client, owner_conn, es, tb, "B doc", f"{SECRET} lives only in B."
    )
    # B's chunk id re-indexed as if A owned it.
    await index_raw(
        es,
        chunk_id=rows_b[0]["id"],
        tenant_id=ta["id"],
        document_id=doc_b,
        content=f"{SECRET} lives only in B.",
    )

    response = await client.post(
        URL, json={"query": SECRET, "k": 50}, headers=auth_headers(ta)
    )

    assert response.status_code == 200
    assert str(rows_b[0]["id"]) not in response.text
    assert SECRET not in response.text
    assert "B doc" not in response.text
    assert response.json()["degraded"] == []


async def test_body_tenant_id_is_422_and_nothing_runs(
    client: AsyncClient,
    two_tenants_seeded: dict[str, SeededTenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    calls: list[object] = []

    async def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)

    monkeypatch.setattr(hybrid_search, "hybrid_search", spy)

    response = await client.post(
        URL,
        json={"query": SHARED, "tenant_id": str(tb["id"])},
        headers=auth_headers(ta),
    )

    assert response.status_code == 422
    assert calls == []


async def test_keyword_candidates_are_not_crowded_out_by_another_tenant(
    client: AsyncClient,
    two_tenants_seeded: dict[str, SeededTenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ES query itself filters by tenant: B's many better matches must not
    take A's keyword candidate slots (hydration would drop them, leaving A empty)."""
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    await upload(client, ta, "A doc", f"{SHARED} appears once in tenant a")
    for i in range(6):
        await upload(client, tb, f"B doc {i}", f"{SHARED} {SHARED} {SHARED} b{i}")
    await get_es().indices.refresh(index=es_client.alias_name())
    monkeypatch.setattr(settings, "hybrid_candidates", 2)

    hits = (
        await client.post(URL, json={"query": SHARED}, headers=auth_headers(ta))
    ).json()["results"]

    assert [h["document_title"] for h in hits] == ["A doc"]
    assert "keyword" in hits[0]["found_by"]
