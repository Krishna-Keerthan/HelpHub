import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, decode_access_token
from app.db.models import User
from app.db.repositories import users as users_repo
from app.db.tenant_context import tenant_transaction
from app.services.auth import parse_uuid
from app.services.embeddings import EmbeddingProvider, default_provider

bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict[str, Any]:
    if credentials is None:
        raise _unauthorized()
    try:
        return decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _unauthorized() from None


Claims = Annotated[dict[str, Any], Depends(get_claims)]


def _tenant_id(claims: dict[str, Any]) -> uuid.UUID:
    tenant_id = parse_uuid(claims["tid"])
    if tenant_id is None:
        raise _unauthorized()
    return tenant_id


async def get_tenant_session(claims: Claims) -> AsyncIterator[AsyncSession]:
    async with tenant_transaction(_tenant_id(claims)) as session:
        yield session


# scope="function": the commit after the yield runs before the response is
# sent, so a failed commit becomes an error response instead of a silent one.
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session, scope="function")]


async def get_current_user(claims: Claims, session: TenantSession) -> User:
    user_id = parse_uuid(claims["sub"])
    if user_id is None:
        raise _unauthorized()
    user = await users_repo.get_by_id(session, _tenant_id(claims), user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user, scope="function")]


async def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user


AdminUser = Annotated[User, Depends(require_admin, scope="function")]


@dataclass(frozen=True)
class Principal:
    """The authenticated user as plain data; holds no session."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


async def get_current_principal(claims: Claims) -> Principal:
    """Verify the token and load the user in a short transaction.

    The transaction is closed before this returns, so a route using this
    (instead of CurrentUser/TenantSession) holds no connection while it does
    slow work such as embedding.
    """
    tenant_id = _tenant_id(claims)
    user_id = parse_uuid(claims["sub"])
    if user_id is None:
        raise _unauthorized()
    async with tenant_transaction(tenant_id) as session:
        user = await users_repo.get_by_id(session, tenant_id, user_id)
        if user is None or not user.is_active:
            raise _unauthorized()
        return Principal(user_id=user.id, tenant_id=user.tenant_id, role=user.role)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def get_embedding_provider() -> EmbeddingProvider:
    return default_provider()


Embedder = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]
