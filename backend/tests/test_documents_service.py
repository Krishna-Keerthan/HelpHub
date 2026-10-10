import hashlib

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.services import documents as documents_service
from tests.conftest import MakeTenant, auth_headers
from tests.ingestion_helpers import CONTENT, owner_document


async def _document_count(owner_conn: AsyncConnection, tenant_id) -> int:
    result = await owner_conn.execute(
        text("SELECT count(*) FROM documents WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    count = result.scalar_one()
    await owner_conn.rollback()
    return count


async def test_nul_bytes_stripped_and_newlines_kept(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    content = "Hello\x00 world.\r\n\r\nSecond\x00 paragraph.\n\n\n"
    stored = "Hello world.\r\n\r\nSecond paragraph.\n\n\n"

    document, created = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", content
    )

    assert created is True
    row = await owner_document(owner_conn, document.id)
    assert row is not None
    assert row["raw_text"] == stored
    assert row["content_hash"] == hashlib.sha256(stored.encode()).hexdigest()
    assert row["status"] == "PENDING"


async def test_created_by_is_the_creating_user(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    row = await owner_document(owner_conn, document.id)
    assert row is not None and row["created_by"] == tenant["user_id"]


@pytest.mark.parametrize("content", ["", "   \n\t\r\n", "\x00\x00", " \x00 "], ids=repr)
async def test_empty_content_rejected(
    owner_conn: AsyncConnection, make_tenant: MakeTenant, content: str
) -> None:
    tenant = await make_tenant()
    with pytest.raises(documents_service.EmptyDocument):
        await documents_service.create_or_get(
            tenant["id"], tenant["user_id"], "Doc", content
        )
    assert await _document_count(owner_conn, tenant["id"]) == 0


async def test_oversize_content_rejected(
    monkeypatch: pytest.MonkeyPatch,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    monkeypatch.setattr(settings, "max_document_chars", 10)

    with pytest.raises(documents_service.DocumentTooLarge):
        await documents_service.create_or_get(
            tenant["id"], tenant["user_id"], "Doc", "x" * 11
        )
    assert await _document_count(owner_conn, tenant["id"]) == 0

    # The limit applies after NUL stripping, and exactly the limit is fine.
    _, created = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", "x" * 10 + "\x00\x00"
    )
    assert created is True


def test_max_document_chars_default() -> None:
    assert type(settings).model_fields["max_document_chars"].default == 500_000


# --- HTTP ---------------------------------------------------------------------


async def test_post_empty_document_is_422(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await client.post(
        "/documents",
        json={"title": "Doc", "content": " \n\x00 "},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 422
    assert await _document_count(owner_conn, tenant["id"]) == 0


async def test_post_oversize_document_is_413(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    monkeypatch.setattr(settings, "max_document_chars", 10)
    response = await client.post(
        "/documents",
        json={"title": "Doc", "content": "x" * 11},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 413
    assert await _document_count(owner_conn, tenant["id"]) == 0


async def test_post_sets_created_by_to_uploader(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    uploader = await make_tenant(role="agent")
    response = await client.post(
        "/documents",
        json={"title": "Doc", "content": CONTENT},
        headers=auth_headers(uploader),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created_by"] == str(uploader["user_id"])
    assert "raw_text" not in body
    row = await owner_document(owner_conn, body["id"])
    assert row is not None and row["created_by"] == uploader["user_id"]


async def test_list_documents_limit_bounds(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    headers = auth_headers(tenant)
    for limit in (0, 101):
        response = await client.get(f"/documents?limit={limit}", headers=headers)
        assert response.status_code == 422
    assert (
        await client.get("/documents?limit=100", headers=headers)
    ).status_code == 200
