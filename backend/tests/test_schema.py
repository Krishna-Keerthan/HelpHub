from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


@pytest.fixture
async def owner_conn() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


@pytest.mark.parametrize("table", ["tenants", "users"])
async def test_table_exists(owner_conn: AsyncConnection, table: str) -> None:
    result = await owner_conn.execute(
        text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}
    )
    assert result.scalar_one() is not None


async def test_vector_extension_installed(owner_conn: AsyncConnection) -> None:
    result = await owner_conn.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    )
    assert result.scalar_one_or_none() == 1


async def test_app_role_is_not_privileged(owner_conn: AsyncConnection) -> None:
    result = await owner_conn.execute(
        text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'helphub_app'"
        )
    )
    row = result.one()
    assert row.rolsuper is False
    assert row.rolbypassrls is False
