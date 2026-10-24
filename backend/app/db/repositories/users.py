import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class DuplicateEmail(Exception):
    """The tenant already has a user with this email."""


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
    try:
        await session.flush()
    except IntegrityError as exc:
        cause = exc.orig.__cause__ if exc.orig is not None else None
        if getattr(cause, "constraint_name", None) == "uq_users_tenant_id_email":
            raise DuplicateEmail from exc
        raise
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
