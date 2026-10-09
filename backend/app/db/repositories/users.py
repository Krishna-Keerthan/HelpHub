import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def get_by_email(
    session: AsyncSession, tenant_id: uuid.UUID, email: str
) -> User | None:
    result = await session.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    )
    return result.scalar_one_or_none()


async def get_by_id(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> User | None:
    result = await session.execute(
        select(User).where(User.tenant_id == tenant_id, User.id == user_id)
    )
    return result.scalar_one_or_none()


async def create(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    email: str,
    password_hash: str,
    role: str,
) -> User:
    user = User(
        tenant_id=tenant_id, email=email, password_hash=password_hash, role=role
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def list_by_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, *, limit: int, offset: int
) -> list[User]:
    result = await session.execute(
        select(User)
        .where(User.tenant_id == tenant_id)
        .order_by(User.created_at, User.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())
