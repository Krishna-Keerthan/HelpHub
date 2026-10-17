import os
from collections.abc import AsyncIterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# hide_parameters: bound values (document text, hashes, emails) never appear in
# exception messages or logs.
# Identifies this process's connections in pg_stat_activity. Fixed at import:
# a process forked after this (e.g. the Day 9 worker) keeps the parent's pid
# unless it builds its own engine.
APPLICATION_NAME = f"helphub-{os.getpid()}"

engine = create_async_engine(
    url=settings.database_url,
    pool_pre_ping=True,
    hide_parameters=True,
    connect_args={"server_settings": {"application_name": APPLICATION_NAME}},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# The session type for annotations in services and api (they do not import
# sqlalchemy themselves).
DbSession = AsyncSession


async def get_session() -> AsyncIterable[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def ping() -> None:
    """SELECT 1 through the runtime (app) role; raises if the database is unreachable."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
