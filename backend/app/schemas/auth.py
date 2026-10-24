from pydantic import BaseModel, Field

from app.schemas.types import LoginPassword, NewPassword, NormalizedEmail, Slug


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=200)
    tenant_slug: Slug
    email: NormalizedEmail
    password: NewPassword


class LoginRequest(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=100)
    email: NormalizedEmail
    password: LoginPassword


class RefreshRequest(BaseModel):
    # Verified as a signed token before anything else; the cap only bounds input.
    refresh_token: str = Field(min_length=1, max_length=2048)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth token type, not a secret)
