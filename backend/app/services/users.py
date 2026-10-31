import uuid

from app.core.security import hash_password_async
from app.db.models import User
from app.db.repositories import users as users_repo
from app.db.session import DbSession
from app.schemas.user import UserCreate

DuplicateEmail = users_repo.DuplicateEmail  # raised by the repository
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


class UserNotFound(Exception):
    pass


async def list_users(
    session: DbSession,
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
    session: DbSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> User:
    user = await users_repo.get_by_id(session, tenant_id, user_id)
    if user is None:
        raise UserNotFound
    return user


async def create_user(
    session: DbSession, tenant_id: uuid.UUID, data: UserCreate
) -> User:
    # Waits for the hash slot while this request's session is open: admin-only,
    # low volume.
    password_hash = await hash_password_async(data.password)
    # The repository flushes, so the INSERT (and its unique check) runs here,
    # while the request is still open, not at commit time.
    return await users_repo.create(
        session,
        tenant_id,
        email=data.email,
        password_hash=password_hash,
        role=data.role,
    )
