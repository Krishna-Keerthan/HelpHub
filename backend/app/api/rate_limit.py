"""Rate-limit dependencies. 429 is sent before any embedding, LLM or hashing work."""

from fastapi import Depends, HTTPException, status

from app.api.deps import CurrentPrincipal
from app.core.config import settings
from app.core.ratelimit import limiter
from app.schemas.auth import LoginRequest


def _enforce(key: str, limit: int) -> None:
    if not settings.rate_limit_enabled:
        return
    retry_after = limiter.hit(key, limit, settings.rate_limit_window_seconds)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def enforce_login(data: LoginRequest) -> None:
    """Called from the route with the parsed body (not a dependency: a body-model
    parameter there would make FastAPI expect a nested body)."""
    account = f"login:{data.tenant_slug.lower()}:{data.email}"
    _enforce(account, settings.rate_limit_login_per_account)
    _enforce("login:*", settings.rate_limit_login_global)


def limit_search(principal: CurrentPrincipal) -> None:
    _enforce(
        f"search:{principal.tenant_id}:{principal.user_id}",
        settings.rate_limit_search_per_user,
    )


def limit_chat(principal: CurrentPrincipal) -> None:
    _enforce(
        f"chat:{principal.tenant_id}:{principal.user_id}",
        settings.rate_limit_chat_per_user,
    )


SearchLimit = Depends(limit_search)
ChatLimit = Depends(limit_chat)
