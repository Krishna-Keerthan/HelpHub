import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.repositories import documents as documents_repo
from app.db.session import engine
from app.services import documents as documents_service
from app.services.embeddings import EmbeddingProvider, FakeEmbeddingProvider
from tests.conftest import MakeTenant
from tests.ingestion_helpers import (
    CONTENT,
    FailingProvider,
    SpyProvider,
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


async def test_failure_to_record_failed_still_raises_ingestion_error(
    monkeypatch: pytest.MonkeyPatch,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    original = documents_repo.set_status

    async def broken_set_status(*args, **kwargs):
        if args[3] == "FAILED":
            raise ConnectionError("database went away")
        return await original(*args, **kwargs)

    monkeypatch.setattr(documents_repo, "set_status", broken_set_status)

    with pytest.raises(documents_service.IngestionError) as exc_info:
        await documents_service.ingest_document(
            tenant["id"], document.id, FailingProvider()
        )
    # The original error is kept, not the one from recording FAILED.
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    row = await owner_document(owner_conn, document.id)
    assert row is not None and row["status"] == "PENDING"


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


async def test_failure_after_another_worker_succeeded_keeps_ready(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    """A late failure must not flip a document another worker made READY."""
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )

    async def other_worker_wins_then_fail() -> None:
        await documents_service.ingest_document(
            tenant["id"], document.id, FakeEmbeddingProvider()
        )
        raise RuntimeError("this worker's model crashed")

    with pytest.raises(documents_service.IngestionError):
        await documents_service.ingest_document(
            tenant["id"], document.id, SpyProvider(other_worker_wins_then_fail)
        )

    row = await owner_document(owner_conn, document.id)
    assert row is not None
    assert row["status"] == "READY"
    assert row["error"] is None
    assert len(await owner_chunks(owner_conn, document.id)) > 1
