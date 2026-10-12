from pathlib import Path

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


def test_valid_settings_accepted() -> None:
    assert make_settings().jwt_algorithm == "HS256"


def test_secret_of_minimum_length_accepted() -> None:
    assert make_settings(jwt_secret="y" * 32).jwt_secret == "y" * 32


@pytest.mark.parametrize("secret", ["", "short", "z" * 31])
def test_short_secret_rejected(secret: str) -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        make_settings(jwt_secret=secret)


def test_placeholder_secret_rejected() -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        make_settings(jwt_secret=JWT_SECRET_PLACEHOLDER)


def test_env_example_ships_the_rejected_placeholder() -> None:
    env_example = Path(__file__).resolve().parents[3] / ".env.example"
    assert (
        f"JWT_SECRET={JWT_SECRET_PLACEHOLDER}" in env_example.read_text().splitlines()
    )


@pytest.mark.parametrize("algorithm", ["HS256", "HS384", "HS512"])
def test_allowed_algorithms_accepted(algorithm: str) -> None:
    assert make_settings(jwt_algorithm=algorithm).jwt_algorithm == algorithm


@pytest.mark.parametrize("algorithm", ["none", "RS256", "hs256", ""])
def test_other_algorithms_rejected(algorithm: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(jwt_algorithm=algorithm)
