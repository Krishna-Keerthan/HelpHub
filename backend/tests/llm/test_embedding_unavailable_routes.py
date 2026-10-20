"""A hosted-embedding failure becomes a generic 503 (or SSE error code), never a 500."""

from collections.abc import Sequence

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_embedding_provider
from app.main import app
from app.services.embeddings import EmbeddingUnavailableError, FakeEmbeddingProvider
from tests.chat.test_chat_api import parse_sse, stream
from tests.conftest import MakeTenant, auth_headers
from tests.helpers.ingestion_helpers import CONTENT, owner_document


class UnavailableEmbedder(FakeEmbeddingProvider):
    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingUnavailableError()

    async def embed_query(self, text: str) -> list[float]:
        raise EmbeddingUnavailableError()


async def test_search_returns_generic_503(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    app.dependency_overrides[get_embedding_provider] = UnavailableEmbedder
    tenant = await make_tenant()
    response = await client.post(
        "/search", json={"query": "q"}, headers=auth_headers(tenant)
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Embedding service unavailable"}


async def test_upload_returns_503_and_marks_the_document_failed(
    client: AsyncClient, make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    app.dependency_overrides[get_embedding_provider] = UnavailableEmbedder
    tenant = await make_tenant()
    response = await client.post(
        "/documents",
        json={"title": "Doc", "content": CONTENT},
        headers=auth_headers(tenant),
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Embedding service unavailable"}
    listed = await client.get("/documents", headers=auth_headers(tenant))
    row = await owner_document(owner_conn, listed.json()[0]["id"])
    assert row is not None and row["status"] == "FAILED"
    assert row["error"] == "EmbeddingUnavailableError: embedding provider unavailable"


async def test_chat_stream_reports_embedding_unavailable(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    app.dependency_overrides[get_embedding_provider] = UnavailableEmbedder
    tenant = await make_tenant()
    response = await stream(client, tenant, {"message": "q"})
    events = parse_sse(response.text)
    assert [n for n, _ in events] == ["error"]
    assert events[0][1]["code"] == "embedding_unavailable"
