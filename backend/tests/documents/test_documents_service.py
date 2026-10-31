import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.services import documents as documents_service
from tests.conftest import MakeTenant


async def _document_count(owner_conn: AsyncConnection, tenant_id) -> int:
    result = await owner_conn.execute(
        text("SELECT count(*) FROM documents WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    count = result.scalar_one()
    await owner_conn.rollback()
    return count


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


# --- HTTP ---------------------------------------------------------------------
