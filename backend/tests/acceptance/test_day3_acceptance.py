"""Day 3 end-to-end acceptance with the REAL embedding model (slow).

Two tenants register and log in through the API, upload documents, search,
and delete. The autouse fake-provider override is removed for this test only.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_embedding_provider
from app.main import app
from tests.conftest import SEED_PASSWORD, _delete_tenants
from tests.helpers.ingestion_helpers import owner_document

A_DOCS = {
    "password-reset.txt": (
        "To reset your password, open the sign-in page and click 'Forgot "
        "password'. We email you a reset link that is valid for one hour. "
        "Follow it to choose a new password and sign back in to your account."
    ),
    "billing-refunds.txt": (
        "Refunds for annual plans are issued within 14 days of purchase. "
        "Monthly plans are not refundable, but you can cancel at any time "
        "before the next billing date."
    ),
    "api-rate-limits.txt": (
        "The API allows 100 requests per minute per key. Responses include "
        "X-RateLimit-Remaining and X-RateLimit-Reset headers; a 429 status "
        "means you should wait until the reset time."
    ),
}
B_DOCS = {
    "office-hours.txt": "Our office is open Monday to Friday, 9am to 5pm.",
    "shipping-times.txt": "Standard shipping takes three to five business days.",
    "password-reset.txt": A_DOCS["password-reset.txt"],  # same text as A's
}
FORBIDDEN = ("raw_text", "embedding", "used_fallback")


async def _register(client: AsyncClient) -> tuple[str, dict[str, str]]:
    slug = f"t-{uuid.uuid4().hex[:12]}"  # leak-guard pattern
    email = f"owner@{slug}.example.com"
    registered = await client.post(
        "/auth/register",
        json={
            "tenant_name": f"Tenant {slug}",
            "tenant_slug": slug,
            "email": email,
            "password": SEED_PASSWORD,
        },
    )
    assert registered.status_code == 201, registered.text
    login = await client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": email, "password": SEED_PASSWORD},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    return me.json()["tenant_id"], headers


async def _upload_all(
    client: AsyncClient, headers: dict[str, str], docs: dict[str, str]
) -> dict[str, str]:
    ids = {}
    for filename, body in docs.items():
        response = await client.post(
            "/documents/upload",
            files={"file": (filename, body.encode(), "text/plain")},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        ids[filename] = response.json()["id"]
    return ids


async def _search(
    client: AsyncClient, headers: dict[str, str], query: str
) -> list[dict]:
    response = await client.post(
        "/search", json={"query": query, "k": 10}, headers=headers
    )
    assert response.status_code == 200, response.text
    for word in FORBIDDEN:
        assert word not in response.text
    return response.json()


@pytest.mark.slow
@pytest.mark.usefixtures("registration_open")
async def test_day3_acceptance(
    client: AsyncClient, owner_conn: AsyncConnection
) -> None:
    fake = app.dependency_overrides.pop(get_embedding_provider)
    tenant_ids: list[uuid.UUID] = []
    try:
        tid_a, headers_a = await _register(client)
        tid_b, headers_b = await _register(client)
        tenant_ids += [uuid.UUID(tid_a), uuid.UUID(tid_b)]
        a_ids = await _upload_all(client, headers_a, A_DOCS)
        b_ids = await _upload_all(client, headers_b, B_DOCS)

        query = "I forgot my login, how do I get back in?"
        hits_a = await _search(client, headers_a, query)
        top = hits_a[0]
        assert top["document_id"] == a_ids["password-reset.txt"], hits_a
        row = await owner_document(owner_conn, top["document_id"])
        assert row is not None
        assert row["raw_text"][top["char_start"] : top["char_end"]] == top["content"]

        hits_b = await _search(client, headers_b, query)
        assert hits_b
        assert {h["document_id"] for h in hits_b} <= set(b_ids.values())
        assert {h["chunk_id"] for h in hits_a}.isdisjoint(
            {h["chunk_id"] for h in hits_b}
        )

        rate = await _search(client, headers_b, "rate limit headers")
        assert {h["document_id"] for h in rate} <= set(b_ids.values())
        assert "X-RateLimit" not in str(rate)

        reset_id = a_ids["password-reset.txt"]
        deleted = await client.delete(f"/documents/{reset_id}", headers=headers_a)
        assert deleted.status_code == 204
        after = await _search(client, headers_a, query)
        assert reset_id not in {h["document_id"] for h in after}
        for path in (f"/documents/{a_ids['billing-refunds.txt']}", "/documents"):
            response = await client.get(path, headers=headers_a)
            assert response.status_code == 200
            for word in FORBIDDEN:
                assert word not in response.text
    finally:
        app.dependency_overrides[get_embedding_provider] = fake
        leaked = await _delete_tenants(tenant_ids)
        assert not leaked, leaked
