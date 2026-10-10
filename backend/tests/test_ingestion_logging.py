"""Ingestion failure logs carry class name, SQLSTATE and ids only."""

import logging
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import chunks as chunks_repo
from app.db.repositories import documents as documents_repo
from app.services import documents as documents_service
from app.services.embeddings import FakeEmbeddingProvider
from tests.conftest import MakeTenant
from tests.ingestion_helpers import CONTENT, FailingProvider

LOGGER = "app.services.documents"
MARKER = "SECRET-CHUNK-TEXT-5c1e"


def _assert_clean(caplog: pytest.LogCaptureFixture) -> None:
    assert caplog.records, "nothing was logged"
    for record in caplog.records:
        assert record.exc_info is None  # no traceback
    assert "Traceback" not in caplog.text
    assert MARKER not in caplog.text
    assert "Paragraph" not in caplog.text  # document content


async def test_provider_failure_logs_no_message_or_traceback(
    caplog: pytest.LogCaptureFixture, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )

    with (
        caplog.at_level(logging.ERROR, logger=LOGGER),
        pytest.raises(documents_service.IngestionError),
    ):
        await documents_service.ingest_document(
            tenant["id"], document.id, FailingProvider()
        )

    _assert_clean(caplog)
    assert "error=RuntimeError" in caplog.text
    assert f"document={document.id}" in caplog.text
    assert f"tenant={tenant['id']}" in caplog.text
    assert "sqlstate=-" in caplog.text


async def test_db_error_logs_sqlstate_not_driver_message(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )

    async def failing_insert(session: AsyncSession, *args, **kwargs) -> None:
        # A server-side error whose message echoes the bound value:
        # invalid input syntax for type integer: "<value>" (SQLSTATE 22P02).
        # The inner text cast keeps asyncpg from rejecting it client-side.
        await session.execute(
            text("SELECT CAST(CAST(:v AS text) AS integer)"), {"v": MARKER}
        )

    monkeypatch.setattr(chunks_repo, "insert_many", failing_insert)

    with (
        caplog.at_level(logging.ERROR, logger=LOGGER),
        pytest.raises(documents_service.IngestionError) as exc_info,
    ):
        await documents_service.ingest_document(
            tenant["id"], document.id, FakeEmbeddingProvider()
        )

    # Non-vacuous: the driver message really contains the value...
    assert MARKER in str(exc_info.value.__cause__)
    # ...and the log does not.
    _assert_clean(caplog)
    assert "sqlstate=22P02" in caplog.text


async def test_failure_to_mark_failed_is_logged_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    make_tenant: MakeTenant,
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    original = documents_repo.set_status

    async def broken_set_status(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        status: str,
        **kwargs,
    ):
        if status == "FAILED":
            raise ConnectionError(f"lost connection while writing {MARKER}")
        return await original(session, tenant_id, document_id, status, **kwargs)

    monkeypatch.setattr(documents_repo, "set_status", broken_set_status)

    with (
        caplog.at_level(logging.ERROR, logger=LOGGER),
        pytest.raises(documents_service.IngestionError),
    ):
        await documents_service.ingest_document(
            tenant["id"], document.id, FailingProvider()
        )

    _assert_clean(caplog)
    assert "could not mark document FAILED" in caplog.text
    assert "error=ConnectionError" in caplog.text
