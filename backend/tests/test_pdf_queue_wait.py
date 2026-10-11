"""Uploads queued behind busy PDF workers wait a bounded time, then get 503."""

import asyncio
import time

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import MakeTenant, auth_headers
from tests.pdf_helpers import text_operator_bomb
from tests.test_pdf_extraction_limits import _live_pdf_workers

UPLOADS = 6
BOMB_OPERATORS = 150_000  # ~2 s of extraction per worker


async def test_queued_pdf_uploads_get_503_after_bounded_wait(
    monkeypatch: pytest.MonkeyPatch, client: AsyncClient, make_tenant: MakeTenant
) -> None:
    monkeypatch.setattr(settings, "pdf_max_concurrency", 2)
    monkeypatch.setattr(settings, "pdf_queue_wait_seconds", 0.3)
    monkeypatch.setattr(settings, "pdf_timeout_seconds", 30.0)
    monkeypatch.setattr(settings, "pdf_cpu_seconds", 60)
    # The semaphore is created lazily with the setting at first use.
    monkeypatch.setattr("app.services.extraction._semaphore", None)
    tenant = await make_tenant()
    bomb = text_operator_bomb(BOMB_OPERATORS)

    peak = 0
    stop = asyncio.Event()

    async def sample() -> None:
        nonlocal peak
        while not stop.is_set():
            peak = max(peak, len(_live_pdf_workers()))
            await asyncio.sleep(0.02)

    sampler = asyncio.create_task(sample())
    started = time.monotonic()
    try:
        async with asyncio.timeout(25):
            responses = await asyncio.gather(
                *(
                    client.post(
                        "/documents/upload",
                        files={"file": (f"d{i}.pdf", bomb, "application/pdf")},
                        headers=auth_headers(tenant),
                    )
                    for i in range(UPLOADS)
                )
            )
    finally:
        stop.set()
        await sampler
    elapsed = time.monotonic() - started

    rejected = [r for r in responses if r.status_code == 503]
    assert rejected, [r.status_code for r in responses]
    assert len(rejected) <= UPLOADS - 2  # the two that got workers are not 503
    for r in rejected:
        assert r.headers["retry-after"].isdigit()
    assert peak <= 2
    assert elapsed < 15
    await asyncio.sleep(0.2)
    assert _live_pdf_workers() == []
