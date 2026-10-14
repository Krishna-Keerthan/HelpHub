from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterResponse(TokenResponse):
    user: UserRead


@router.post(
    "/register", status_code=status.HTTP_201_CREATED, response_model=RegisterResponse
)
async def register(data: RegisterRequest) -> RegisterResponse:
    try:
        user, token = await auth_service.register_tenant(data)
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
    return RegisterResponse(access_token=token, user=UserRead.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest) -> TokenResponse:
    try:
        token = await auth_service.authenticate(data)
    except auth_service.InvalidCredentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
