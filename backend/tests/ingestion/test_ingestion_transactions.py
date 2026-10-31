"""No database transaction may be open while embedding runs."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_embedding_provider
from app.main import app
from app.services import documents as documents_service
from tests.conftest import MakeTenant, auth_headers
from tests.helpers.ingestion_helpers import CONTENT, SpyProvider, idle_in_transaction


async def test_no_transaction_open_during_embedding(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    seen: list[int] = []

    async def check() -> None:
        seen.append(await idle_in_transaction(owner_conn))

    spy = SpyProvider(check)
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    ingested = await documents_service.ingest_document(tenant["id"], document.id, spy)

    assert ingested.status == "READY"
    assert spy.calls == 1
    assert seen == [0]


async def test_post_documents_holds_no_transaction_during_embedding(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    seen: list[int] = []

    async def check() -> None:
        seen.append(await idle_in_transaction(owner_conn))

    spy = SpyProvider(check)
    app.dependency_overrides[get_embedding_provider] = lambda: spy

    response = await client.post(
        "/documents",
        json={"title": "Doc", "content": CONTENT},
        headers=auth_headers(tenant),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "READY"
    assert spy.calls == 1
    assert seen == [0]
