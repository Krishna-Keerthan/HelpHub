import logging

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser
from app.api.rate_limit import enforce_login
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services import auth as auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterResponse(TokenResponse):
    user: UserRead


@router.post(
    "/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse
)
async def register(data: RegisterRequest) -> RegisterResponse:
    try:
        user, tokens = await auth_service.register_tenant(data)
    except auth_service.RegistrationDisabled:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Registration is disabled"
        ) from None
    except auth_service.ReservedSlug:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="slug not available"
        ) from None
    except auth_service.TenantSlugTaken:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Tenant slug already taken"
        ) from None
    return RegisterResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest) -> TokenResponse:
    enforce_login(data)  # 429 before any password hashing
    try:
        tokens = await auth_service.authenticate(data)
    except auth_service.InvalidCredentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return TokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token
    )


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


def _invalid_refresh(reason: str) -> HTTPException:
    # Reason is a fixed label, never token content.
    logger.info("refresh_rejected reason=%s", reason)
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Public by design: the credential is the signed refresh token in the body (an
# access token is rejected here), checked before any database access.
@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest) -> TokenResponse:
    try:
        tokens = await auth_service.refresh(data.refresh_token)
    except auth_service.InvalidRefreshToken as exc:
        raise _invalid_refresh(exc.reason) from None
    return TokenResponse(
        access_token=tokens.access_token, refresh_token=tokens.refresh_token
    )


# Public by design, like /refresh: the credential is the signed refresh token in
# the body, so a client whose access token already expired can still log out.
# Always 204; the outcome is only logged (a fixed label, never token content).
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshRequest) -> Response:
    outcome = await auth_service.logout(data.refresh_token)
    logger.info("logout outcome=%s", outcome)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
