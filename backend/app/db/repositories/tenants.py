import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant
from app.db.session import AsyncSessionLocal


async def get_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


async def create(session: AsyncSession, *, name: str, slug: str) -> Tenant:
    tenant = Tenant(name=name, slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


async def list_ids() -> list[uuid.UUID]:
    """Every tenant id (maintenance scripts). Own session: the tenants table
    is not tenant-scoped."""
    async with AsyncSessionLocal() as session:
        result = await session.scalars(select(Tenant.id).order_by(Tenant.created_at))
        return list(result)
