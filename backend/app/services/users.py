import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models import User
from app.db.repositories import users as users_repo
from app.schemas.user import UserCreate

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


class DuplicateEmail(Exception):
    pass


class UserNotFound(Exception):
    pass


async def list_users(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> list[User]:
    limit = max(1, min(limit, MAX_LIMIT))
    return await users_repo.list_by_tenant(
        session, tenant_id, limit=limit, offset=max(0, offset)
    )


async def get_user(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> User:
    user = await users_repo.get_by_id(session, tenant_id, user_id)
    if user is None:
        raise UserNotFound
    return user


async def create_user(
    session: AsyncSession, tenant_id: uuid.UUID, data: UserCreate
) -> User:
    password_hash = hash_password(data.password)
    try:
        # The repository flushes, so the INSERT (and its unique check) runs
        # here, while the request is still open, not at commit time.
        return await users_repo.create(
            session,
            tenant_id,
            email=data.email,
            password_hash=password_hash,
            role=data.role,
        )
    except IntegrityError as exc:
        cause = exc.orig.__cause__ if exc.orig is not None else None
        if getattr(cause, "constraint_name", None) == "uq_users_tenant_id_email":
            raise DuplicateEmail from exc
        raise
