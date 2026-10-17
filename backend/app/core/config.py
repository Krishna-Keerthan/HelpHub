from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3] / ".env"

# Value shipped in .env.example; must never be used as a real secret.
JWT_SECRET_PLACEHOLDER = "change-me-generate-with-openssl-rand-hex-32"  # noqa: S105 (public placeholder, rejected at startup)
JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    # hide_input_in_errors: a rejected value (e.g. a 31-char JWT secret) is
    # never echoed in a ValidationError.
    model_config = SettingsConfigDict(
        env_file=ROOT, extra="ignore", hide_input_in_errors=True
    )

    # Secrets are SecretStr so reprs, dumps and error messages show
    # '**********'. The aliases keep the env var / keyword names
    # (DATABASE_URL, MIGRATION_DATABASE_URL, JWT_SECRET); the read-only
    # properties below return the plain values for the few call sites.
    database_dsn: SecretStr = Field(validation_alias="database_url")
    migration_database_dsn: SecretStr = Field(validation_alias="migration_database_url")
    # "production" turns on the hardening in app/main.py and the checks below.
    app_env: Literal["local", "test", "production"] = "local"
    jwt_signing_key: SecretStr = Field(validation_alias="jwt_secret")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_minutes: int = 60
    # Off by default: tenants are created by scripts/seed_tenant.py. It is set to
    # true (ALLOW_PUBLIC_REGISTRATION=true) as the last step of the project.
    allow_public_registration: bool = False
    # Browser origins allowed to call the API, comma-separated (CORS_ORIGINS).
    # Empty means no CORS headers at all (same-origin or non-browser clients).
    cors_origins: str = ""
    warm_up_embeddings: bool = True
    # Longest document (in characters, after NUL stripping) accepted for ingestion.
    max_document_chars: int = 500_000
    # Largest accepted upload file; the request body is read with a bounded cap.
    max_upload_bytes: int = 5 * 1024 * 1024
    # PDF text extraction runs in a child process: killed after
    # pdf_timeout_seconds of wall time, with kernel limits on CPU seconds and
    # address space (independent backstops); at most pdf_max_concurrency at once.
    pdf_timeout_seconds: float = 10.0
    pdf_cpu_seconds: int = 10
    pdf_memory_bytes: int = 512 * 1024 * 1024
    pdf_max_concurrency: int = 2
    # Longest an upload waits for a free PDF worker slot before getting 503.
    pdf_queue_wait_seconds: float = 5.0
    # Empty key is allowed at startup; chat requests then fail with llm_unavailable.
    groq_api_key: SecretStr = SecretStr("")
    # Groq retires models without much notice; scripts/smoke_groq.py checks
    # this id against GET /models. openai/gpt-oss-20b is the smaller option.
    groq_model: str = "openai/gpt-oss-120b"
    # Sent only to openai/gpt-oss-* models (other models reject or ignore it).
    llm_reasoning_effort: Literal["low", "medium", "high"] = "low"
    # gpt-oss reasoning tokens are billed against max_completion_tokens even
    # though they are never shown. This is added to the answer budget so
    # reasoning cannot starve the answer (measured: ~5 tokens at "low" for a
    # greeting; a grounded answer needs far more, so 512 is a generous cap).
    llm_reasoning_token_headroom: int = 512
    llm_timeout_seconds: float = 30.0
    # Overall budget for retries before the first token.
    llm_retry_deadline_seconds: float = 20.0
    max_answer_tokens: int = 800
    llm_temperature: float = 0.2
    chat_top_k: int = 5
    chat_history_messages: int = 6
    max_context_chars: int = 12_000
    max_message_chars: int = 2000
    # Below this top-hit score a question gets a refusal and no LLM call
    # (provisional, from scripts/calibrate_threshold.py; see docs/plans/day-04.md).
    min_retrieval_score: float = 0.59

    @field_validator("jwt_signing_key")
    @classmethod
    def _check_jwt_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if secret == JWT_SECRET_PLACEHOLDER:
            raise ValueError("JWT_SECRET is still the .env.example placeholder")
        if len(secret) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET must be at least {JWT_SECRET_MIN_LENGTH} characters"
            )
        return value

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.app_env != "production":
            return self
        if "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must not contain '*' in production")
        if not self.groq_api_key.get_secret_value():
            raise ValueError("GROQ_API_KEY is required in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        return self.database_dsn.get_secret_value()

    @property
    def migration_database_url(self) -> str:
        return self.migration_database_dsn.get_secret_value()

    @property
    def jwt_secret(self) -> str:
        return self.jwt_signing_key.get_secret_value()


settings = Settings()
