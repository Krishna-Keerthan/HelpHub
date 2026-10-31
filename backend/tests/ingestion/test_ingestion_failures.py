import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.session import engine
from app.services import documents as documents_service
from app.services.embeddings import EmbeddingProvider
from tests.conftest import MakeTenant
from tests.helpers.ingestion_helpers import (
    CONTENT,
    FailingProvider,
    WrongCountProvider,
    WrongDimProvider,
    owner_chunks,
    owner_document,
)


@pytest.mark.parametrize(
    ("provider", "expected_error"),
    [
        # Foreign exception: class name only, its message may carry content.
        (FailingProvider(), "RuntimeError"),
        (WrongCountProvider(), "EmbeddingError: expected "),
        (WrongDimProvider(), "EmbeddingError: vector 0 has length 383"),
    ],
    ids=["raises", "wrong-count", "wrong-dimension"],
)
async def test_failed_ingestion_marks_document_failed(
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    provider: EmbeddingProvider,
    expected_error: str,
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )

    with pytest.raises(documents_service.IngestionError):
        await documents_service.ingest_document(tenant["id"], document.id, provider)

    row = await owner_document(owner_conn, document.id)
    assert row is not None  # the document survives the failure
    assert row["status"] == "FAILED"
    assert row["error"].startswith(expected_error)
    assert len(row["error"]) <= documents_service.ERROR_MAX_CHARS
    assert "Paragraph" not in row["error"]
    assert await owner_chunks(owner_conn, document.id) == []


async def test_db_errors_never_include_bound_parameters() -> None:
    marker = "SECRET-BOUND-PARAMETER-7f3a"
    with pytest.raises(DBAPIError) as exc_info:
        async with engine.connect() as conn:
            # The server does not echo the parameter for division by zero, so
            # only SQLAlchemy's "[parameters: ...]" suffix could leak it.
            await conn.execute(
                text("SELECT 1 / 0, CAST(:marker AS text)"), {"marker": marker}
            )
    message = str(exc_info.value)
    assert "division by zero" in message
    assert marker not in message
    assert "hidden due to hide_parameters" in message
