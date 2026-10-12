"""Pinned behaviour: identical content is deduplicated per tenant; a re-post
with a different title returns the existing document unchanged."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import MakeTenant, auth_headers
from tests.helpers.ingestion_helpers import CONTENT, owner_chunks, owner_document


async def test_repost_with_different_title_returns_existing_unchanged(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    headers = auth_headers(tenant)

    first = await client.post(
        "/documents", json={"title": "First", "content": CONTENT}, headers=headers
    )
    assert first.status_code == 201
    doc_id = first.json()["id"]
    row_before = await owner_document(owner_conn, doc_id)
    chunks_before = await owner_chunks(owner_conn, doc_id)

    second = await client.post(
        "/documents", json={"title": "Second", "content": CONTENT}, headers=headers
    )

    assert second.status_code == 200
    assert second.json()["id"] == doc_id
    assert second.json()["title"] == "First"
    assert second.json()["status"] == "READY"
    # Nothing about the stored row or its chunks changed.
    assert await owner_document(owner_conn, doc_id) == row_before
    assert await owner_chunks(owner_conn, doc_id) == chunks_before
