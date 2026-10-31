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


async def test_app_role_is_not_privileged(owner_conn: AsyncConnection) -> None:
    result = await owner_conn.execute(
        text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'helphub_app'"
        )
    )
    row = result.one()
    assert row.rolsuper is False
    assert row.rolbypassrls is False
