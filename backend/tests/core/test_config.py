import pytest
from pydantic import ValidationError

from app.core.config import JWT_SECRET_PLACEHOLDER, Settings

GOOD_SECRET = "x" * 32


def make_settings(**overrides: str) -> Settings:
    values = {
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "migration_database_url": "postgresql+asyncpg://o:p@localhost/db",
        "jwt_secret": GOOD_SECRET,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize("secret", ["", "short", "z" * 31])
def test_short_secret_rejected(secret: str) -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        make_settings(jwt_secret=secret)


def test_placeholder_secret_rejected() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        make_settings(jwt_secret=JWT_SECRET_PLACEHOLDER)
