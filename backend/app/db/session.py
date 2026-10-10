from collections.abc import AsyncIterable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# hide_parameters: bound values (document text, hashes, emails) never appear in
# exception messages or logs.
engine = create_async_engine(
    url=settings.database_url, pool_pre_ping=True, hide_parameters=True
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterable[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
