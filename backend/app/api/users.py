import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser, TenantSession
from app.schemas.user import UserCreate, UserRead
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def list_users(
    user: CurrentUser,
    session: TenantSession,
    limit: Annotated[
        int, Query(ge=1, le=users_service.MAX_LIMIT)
    ] = users_service.DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserRead]:
    users = await users_service.list_users(
        session, user.tenant_id, limit=limit, offset=offset
    )
    return [UserRead.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID, user: CurrentUser, session: TenantSession
) -> UserRead:
    try:
        found = await users_service.get_user(session, user.tenant_id, user_id)
    except users_service.UserNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="User not found"
        ) from None
    return UserRead.model_validate(found)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate, admin: AdminUser, session: TenantSession
) -> UserRead:
    try:
        created = await users_service.create_user(session, admin.tenant_id, data)
    except users_service.DuplicateEmail:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
    return UserRead.model_validate(created)
