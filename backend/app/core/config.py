from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT, extra="ignore")

    database_url: str
    migration_database_url: str
    app_env: str = "local"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60


settings = Settings()
