from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3] / ".env"

# Value shipped in .env.example; must never be used as a real secret.
JWT_SECRET_PLACEHOLDER = "change-me-generate-with-openssl-rand-hex-32"
JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT, extra="ignore")

    database_url: str
    migration_database_url: str
    app_env: str = "local"
    jwt_secret: str
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_minutes: int = 60
    allow_public_registration: bool = True

    @field_validator("jwt_secret")
    @classmethod
    def _check_jwt_secret(cls, value: str) -> str:
        if value == JWT_SECRET_PLACEHOLDER:
            raise ValueError("JWT_SECRET is still the .env.example placeholder")
        if len(value) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET must be at least {JWT_SECRET_MIN_LENGTH} characters"
            )
        return value


settings = Settings()
