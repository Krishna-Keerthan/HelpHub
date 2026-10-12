"""Ingestion failure logs carry traceback frames (file:line) and, for our own
exception types only, the message."""

import logging
import re

import pytest

from app.services import documents as documents_service
from app.services.embeddings import EmbeddingProvider
from tests.conftest import MakeTenant
from tests.helpers.ingestion_helpers import CONTENT, FailingProvider, WrongCountProvider

LOGGER = "app.services.documents"
FRAME = re.compile(r"[\w.]+\.py:\d+ in \w+")


async def _fail_ingestion(
    caplog: pytest.LogCaptureFixture,
    make_tenant: MakeTenant,
    provider: EmbeddingProvider,
) -> str:
    tenant = await make_tenant()
    document, _ = await documents_service.create_or_get(
        tenant["id"], tenant["user_id"], "Doc", CONTENT
    )
    with (
        caplog.at_level(logging.ERROR, logger=LOGGER),
        pytest.raises(documents_service.IngestionError),
    ):
        await documents_service.ingest_document(tenant["id"], document.id, provider)
    [record] = caplog.records
    assert record.exc_info is None
    return record.getMessage()


async def test_foreign_exception_logs_frames_but_no_message(
    caplog: pytest.LogCaptureFixture, make_tenant: MakeTenant
) -> None:
    line = await _fail_ingestion(caplog, make_tenant, FailingProvider())

    assert "error=RuntimeError" in line
    frames = line.split("frames=", 1)[1]
    # Down to where the provider raised, through the service.
    assert re.search(r"documents\.py:\d+ in _embed_and_store", frames), frames
    assert re.search(r"ingestion_helpers\.py:\d+ in embed_passages", frames), frames
    assert FRAME.search(frames)
    assert "message=" not in line
    assert FailingProvider.MESSAGE not in line
    assert "Traceback" not in line


async def test_own_exception_logs_its_message(
    caplog: pytest.LogCaptureFixture, make_tenant: MakeTenant
) -> None:
    line = await _fail_ingestion(caplog, make_tenant, WrongCountProvider())

    assert "error=EmbeddingError" in line
    assert re.search(r"message=expected \d+ vectors, got \d+", line), line
    assert "frames=" in line
