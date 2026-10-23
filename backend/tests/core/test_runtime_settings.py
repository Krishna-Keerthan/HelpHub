"""The running app needs only the runtime variables; the owner URL is for alembic."""

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main_module
from app.core.config import Settings

RUNTIME_ONLY = {
    "database_url": "postgresql+asyncpg://x:y@localhost/db",
    "jwt_secret": "k" * 40,
}


def runtime_settings() -> Settings:
    return Settings(_env_file=None, **RUNTIME_ONLY)  # type: ignore[arg-type]


def test_settings_load_without_the_migration_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    assert runtime_settings().migration_database_dsn is None


def test_reading_the_migration_url_without_it_names_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="MIGRATION_DATABASE_URL"):
        _ = runtime_settings().migration_database_url


async def test_app_serves_health_with_only_runtime_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setattr(main_module, "settings", runtime_settings())

    transport = ASGITransport(app=main_module.create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
