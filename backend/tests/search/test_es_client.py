"""Shared Elasticsearch client: readiness, lazy creation, lifespan, ES down."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app, lifespan
from app.services import es_client


async def test_ready_against_real_es() -> None:
    assert await es_client.es_ready() is True


def test_test_session_uses_an_isolated_index_prefix() -> None:
    assert settings.es_index_prefix.startswith("test-")
    assert es_client.alias_name().startswith("test-")


def test_client_is_shared_and_lazy() -> None:
    assert es_client.get_es() is es_client.get_es()


async def test_lifespan_shutdown_closes_the_shared_client() -> None:
    first = es_client.get_es()
    async with lifespan(app):
        pass
    assert es_client._client is None
    assert es_client.get_es() is not first  # recreated lazily after close


async def test_app_and_health_work_with_es_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await es_client.close_es()
    monkeypatch.setattr(settings, "es_endpoint", "http://127.0.0.1:1")
    monkeypatch.setattr(settings, "es_timeout_seconds", 0.5)
    try:
        async with lifespan(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/health")).status_code == 200
            assert await es_client.es_ready() is False
    finally:
        await es_client.close_es()
