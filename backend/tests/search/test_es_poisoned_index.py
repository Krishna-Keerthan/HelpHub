"""Poisoned index defence: an ES hit is only a candidate id. Hydration from
Postgres (explicit tenant_id + RLS) drops anything the tenant does not own."""

import uuid

from elasticsearch import AsyncElasticsearch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services import keyword_search
from app.services.es_client import get_es
from tests.conftest import MakeTenant
from tests.helpers.es_helpers import index_raw, upload_and_index

# gate-allow: secret fake value used only by this test
SECRET = "zq-secret-of-tenant-b"


async def test_chunk_claimed_for_a_but_owned_by_b_is_dropped(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    es: AsyncElasticsearch = get_es()
    a, b = await make_tenant(), await make_tenant()
    doc_b, rows_b = await upload_and_index(
        client, owner_conn, es, b, "B doc", f"{SECRET} lives only in B."
    )
    # The poison: B's chunk id re-indexed as if it belonged to A.
    await index_raw(
        es,
        chunk_id=rows_b[0]["id"],
        tenant_id=a["id"],
        document_id=doc_b,
        content=f"{SECRET} lives only in B.",
    )

    hits = await keyword_search.search(a["id"], "zq-secret-of-tenant-b", 10, es)

    assert hits == []
    assert SECRET not in str(hits)


async def test_unknown_chunk_id_is_silently_dropped(
    make_tenant: MakeTenant,
) -> None:
    es: AsyncElasticsearch = get_es()
    a = await make_tenant()
    await index_raw(
        es,
        chunk_id=uuid.uuid4(),  # no Postgres row at all
        tenant_id=a["id"],
        document_id=uuid.uuid4(),
        content="ghost-chunk-marker without a row",
    )
    assert await keyword_search.search(a["id"], "ghost-chunk-marker", 10, es) == []


async def test_legit_hits_survive_next_to_poisoned_ones(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    es: AsyncElasticsearch = get_es()
    a, b = await make_tenant(), await make_tenant()
    _, rows_a = await upload_and_index(
        client, owner_conn, es, a, "A doc", "zq-shared-marker is described here."
    )
    doc_b, rows_b = await upload_and_index(
        client, owner_conn, es, b, "B doc", "zq-shared-marker zq-shared-marker B."
    )
    await index_raw(
        es,
        chunk_id=rows_b[0]["id"],
        tenant_id=a["id"],
        document_id=doc_b,
        content="zq-shared-marker zq-shared-marker B.",
    )

    hits = await keyword_search.search(a["id"], "zq-shared-marker", 10, es)

    assert [h.hit.chunk_id for h in hits] == [rows_a[0]["id"]]
    assert hits[0].document_title == "A doc"
