import logging

import pytest
from httpx import AsyncClient

from app.db.session import ping
from app.services import health


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_runs_select_1_through_the_app_role(client: AsyncClient) -> None:
    await ping()  # raises if the runtime engine cannot reach the database

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_not_ready_when_the_database_fails_and_nothing_leaks(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def broken() -> None:
        raise ConnectionRefusedError("postgres://user:SECRET-PW@db/x")

    monkeypatch.setattr(health, "ping", broken)
    with caplog.at_level(logging.ERROR, logger="app.services.health"):
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "not ready"}
    assert "ConnectionRefusedError" in caplog.text
    assert "SECRET-PW" not in caplog.text
    assert "SECRET-PW" not in response.text


async def test_not_ready_when_the_database_hangs(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    async def hangs() -> None:
        await asyncio.sleep(60)

    monkeypatch.setattr(health, "ping", hangs)
    monkeypatch.setattr(health.settings, "ready_timeout_seconds", 0.05)

    response = await client.get("/health/ready")

    assert response.status_code == 503
