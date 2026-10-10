import pytest
from sqlalchemy import text

from tests.conftest import auth_headers

# Several paragraphs so the chunker produces more than one chunk.
CONTENT = "\n\n".join(
    f"Paragraph {i}: " + "Testing ingestion idempotency behavior twice. " * 12
    for i in range(6)
)


async def _chunk_count(owner_conn, document_id) -> int:
    result = await owner_conn.execute(
        text("SELECT count(*) FROM chunks WHERE document_id = :id"),
        {"id": document_id},
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_ingestion_idempotency(client, owner_conn, two_tenants_seeded):
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]
    headers = auth_headers(ta)
    payload = {"title": "Idempotent Doc", "content": CONTENT}

    # Ingest twice: first creates (201), second returns the existing row (200).
    first = await client.post("/documents", json=payload, headers=headers)
    assert first.status_code == 201
    assert first.json()["status"] == "READY"
    doc_id = first.json()["id"]
    chunks_after_first = await _chunk_count(owner_conn, doc_id)
    assert chunks_after_first > 1

    second = await client.post("/documents", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json()["id"] == doc_id

    # Assert chunk counts remain identical
    assert await _chunk_count(owner_conn, doc_id) == chunks_after_first
    listing = await client.get("/documents", headers=headers)
    assert [d["id"] for d in listing.json()].count(doc_id) == 1

    # The same content in another tenant is a different document.
    other = await client.post("/documents", json=payload, headers=auth_headers(tb))
    assert other.status_code == 201
    assert other.json()["id"] != doc_id
