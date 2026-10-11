from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.core.security import InvalidTokenError, TokenSubject, parse_token_subject
from app.db.models import User
from app.db.repositories import users as users_repo
from app.db.tenant_context import tenant_transaction
from app.services.embeddings import EmbeddingProvider, default_provider
from app.services.llm import GroqProvider, LLMProvider

bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_token_subject(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> TokenSubject:
    """Verified user and tenant ids from the bearer token (claims checked once)."""
    if credentials is None:
        raise _unauthorized()
    try:
        return parse_token_subject(credentials.credentials)
    except InvalidTokenError:
        raise _unauthorized() from None


Subject = Annotated[TokenSubject, Depends(get_token_subject)]


async def get_tenant_session(subject: Subject) -> AsyncIterator[AsyncSession]:
    async with tenant_transaction(subject.tenant_id) as session:
        yield session


# scope="function": the commit after the yield runs before the response is
# sent, so a failed commit becomes an error response instead of a silent one.
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session, scope="function")]


async def get_current_user(subject: Subject, session: TenantSession) -> User:
    user = await users_repo.get_by_id(session, subject.tenant_id, subject.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user, scope="function")]


async def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user


AdminUser = Annotated[User, Depends(require_admin, scope="function")]


async def get_current_principal(subject: Subject) -> Principal:
    """Verify the token and load the user in a short transaction.

    The transaction is closed before this returns, so a route using this
    (instead of CurrentUser/TenantSession) holds no connection while it does
    slow work such as embedding.
    """
    async with tenant_transaction(subject.tenant_id) as session:
        user = await users_repo.get_by_id(session, subject.tenant_id, subject.user_id)
        if user is None or not user.is_active:
            raise _unauthorized()
        return Principal(user_id=user.id, tenant_id=user.tenant_id, role=user.role)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def get_embedding_provider() -> EmbeddingProvider:
    return default_provider()


Embedder = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]


_llm_provider: GroqProvider | None = None


def get_llm_provider() -> LLMProvider:
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = GroqProvider()
    return _llm_provider


LLM = Annotated[LLMProvider, Depends(get_llm_provider)]
