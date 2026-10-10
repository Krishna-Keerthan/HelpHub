"""A row vanishing mid-update raises DocumentNotFound, not AssertionError."""

import pytest

from app.db.repositories import documents as documents_repo
from app.services import documents as documents_service
from app.services.embeddings import FakeEmbeddingProvider
from tests.conftest import MakeTenant
from tests.ingestion_helpers import CONTENT, FailingProvider


async def _vanishing_set_status(*args, **kwargs) -> None:
    """set_status whose UPDATE ... RETURNING matched no row (returns None)."""


async def test_retry_reset_on_vanished_row_raises_not_found(
    monkeypatch: pytest.MonkeyPatch, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    with pytest.raises(documents_service.IngestionError):
        await documents_service.ingest_document(
            tenant["id"], document.id, FailingProvider()
        )
    monkeypatch.setattr(documents_repo, "set_status", _vanishing_set_status)

    # FAILED -> PENDING reset finds no row.
    with pytest.raises(documents_service.DocumentNotFound):
        await documents_service.create_or_get(
            tenant["id"], tenant["user_id"], "Doc", CONTENT
        )


async def test_ready_update_on_vanished_row_raises_not_found(
    monkeypatch: pytest.MonkeyPatch, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    monkeypatch.setattr(documents_repo, "set_status", _vanishing_set_status)

    with pytest.raises(documents_service.DocumentNotFound):
        await documents_service.ingest_document(
            tenant["id"], document.id, FakeEmbeddingProvider()
        )
