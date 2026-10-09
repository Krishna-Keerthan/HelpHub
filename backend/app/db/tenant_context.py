import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


async def set_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Scope the session's current transaction to one tenant for RLS.

    The setting is transaction-local (is_local=true), so it cannot leak to the
    next user of a pooled connection, and it resets on commit or rollback.
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


@asynccontextmanager
async def tenant_transaction(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Own session and a single transaction scoped to ``tenant_id``.

    Commits on success; rolls back and re-raises on any error.
    """
    async with AsyncSessionLocal() as session:
        try:
            await set_tenant(session, tenant_id)
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
