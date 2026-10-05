from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT, extra="ignore")

    database_url: str
    migration_database_url: str
    app_env: str = "local"


settings = Settings()
