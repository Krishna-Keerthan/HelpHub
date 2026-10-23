import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.main import create_app

BASE = {
    "database_url": "postgresql+asyncpg://x:y@localhost/db",
    "migration_database_url": "postgresql+asyncpg://x:y@localhost/db",
    "jwt_secret": "k" * 40,
}


def make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})  # type: ignore[arg-type]


def test_public_registration_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOW_PUBLIC_REGISTRATION", raising=False)
    assert make().allow_public_registration is False


def test_unknown_app_env_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make(app_env="prod")


def test_production_requires_a_groq_key() -> None:
    with pytest.raises(ValidationError):
        make(app_env="production", groq_api_key="")
    assert make(app_env="production", groq_api_key="gsk-test").is_production


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError):
        make(app_env="production", groq_api_key="gsk-test", cors_origins="*")
    assert make(app_env="local", cors_origins="*").cors_origin_list == ["*"]


def test_cors_origins_are_split_and_trimmed() -> None:
    parsed = make(cors_origins=" https://a.test , https://b.test,,")
    assert parsed.cors_origin_list == ["https://a.test", "https://b.test"]
    assert make().cors_origin_list == []


async def get(
    monkeypatch: pytest.MonkeyPatch, path: str, **settings_values: object
) -> int:
    for name, value in settings_values.items():
        monkeypatch.setattr(settings, name, value)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return (await client.get(path)).status_code


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_docs_are_served_locally_and_hidden_in_production(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    assert await get(monkeypatch, path, app_env="local") == 200
    assert await get(monkeypatch, path, app_env="production") == 404


async def test_health_still_served_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await get(monkeypatch, "/health", app_env="production") == 200


async def cors_headers(
    monkeypatch: pytest.MonkeyPatch, origin: str, origins: str
) -> tuple[int, dict[str, str]]:
    monkeypatch.setattr(settings, "cors_origins", origins)
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/search",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    return response.status_code, dict(response.headers)


async def test_cors_preflight_allows_only_the_configured_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, headers = await cors_headers(
        monkeypatch, "https://app.test", "https://app.test"
    )
    assert status == 200
    assert headers["access-control-allow-origin"] == "https://app.test"
    assert "access-control-allow-credentials" not in headers

    status, headers = await cors_headers(
        monkeypatch, "https://evil.test", "https://app.test"
    )
    assert "access-control-allow-origin" not in headers


async def test_no_cors_headers_without_configured_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, headers = await cors_headers(monkeypatch, "https://app.test", "")
    assert "access-control-allow-origin" not in headers


@pytest.mark.parametrize("field", ["database_url", "migration_database_url"])
@pytest.mark.parametrize(
    "prefix", ["postgresql://", "postgresql+psycopg://", "postgres://"]
)
def test_database_urls_must_use_the_asyncpg_driver(field: str, prefix: str) -> None:
    url = f"{prefix}user:s3cret-pw@localhost/db"
    with pytest.raises(ValidationError) as exc_info:
        make(**{field: url})
    message = str(exc_info.value)
    assert "postgresql+asyncpg://" in message
    assert "s3cret-pw" not in message and "user:" not in message


def test_asyncpg_urls_are_accepted_and_migration_url_is_optional() -> None:
    assert make().database_url.startswith("postgresql+asyncpg://")
    assert make(migration_database_url=None).database_dsn is not None
