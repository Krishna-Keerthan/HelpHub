"""Secrets in Settings never appear in reprs, dumps or error messages.

They are stored as SecretStr; settings.jwt_secret / database_url /
migration_database_url are read-only accessors returning the plain value.
"""

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings

DB_PASSWORD = "db-pass-4f1c9a"
OWNER_PASSWORD = "owner-pass-82be0d"
JWT = "jwt-secret-" + "k" * 32
SECRETS = (DB_PASSWORD, OWNER_PASSWORD, JWT)


def make_settings(**overrides: str) -> Settings:
    values = {
        "database_url": f"postgresql+asyncpg://app:{DB_PASSWORD}@localhost/db",
        "migration_database_url": f"postgresql+asyncpg://own:{OWNER_PASSWORD}@localhost/db",
        "jwt_secret": JWT,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _assert_hidden(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text


def test_repr_and_str_hide_secrets() -> None:
    settings = make_settings()
    _assert_hidden(repr(settings))
    _assert_hidden(str(settings))
    assert "**********" in repr(settings)


def test_model_dump_hides_secrets() -> None:
    settings = make_settings()
    _assert_hidden(str(settings.model_dump()))
    _assert_hidden(settings.model_dump_json())
    secret_values = [
        v for v in settings.model_dump().values() if isinstance(v, SecretStr)
    ]
    assert len(secret_values) == 4


def test_attribute_error_message_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """The original leak: monkeypatching a missing setting printed the repr."""
    settings = make_settings()
    with pytest.raises(AttributeError) as exc_info:
        monkeypatch.setattr(settings, "no_such_setting", 1)
    _assert_hidden(str(exc_info.value))


def test_accessors_return_plain_values() -> None:
    settings = make_settings()
    assert settings.jwt_secret == JWT
    assert (
        settings.database_url == f"postgresql+asyncpg://app:{DB_PASSWORD}@localhost/db"
    )
    assert (
        settings.migration_database_url
        == f"postgresql+asyncpg://own:{OWNER_PASSWORD}@localhost/db"
    )
    assert all(
        isinstance(v, str)
        for v in (
            settings.jwt_secret,
            settings.database_url,
            settings.migration_database_url,
        )
    )


def test_environment_variable_names_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"postgresql+asyncpg://app:{DB_PASSWORD}@h/db")
    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL", f"postgresql+asyncpg://own:{OWNER_PASSWORD}@h/db"
    )
    monkeypatch.setenv("JWT_SECRET", JWT)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.jwt_secret == JWT
    assert DB_PASSWORD in settings.database_url
    assert OWNER_PASSWORD in settings.migration_database_url


def test_rejected_secret_not_echoed_in_validation_error() -> None:
    almost = "s" * 31  # too short, but could still be a real secret
    with pytest.raises(ValidationError) as exc_info:
        make_settings(jwt_secret=almost)
    assert "at least 32" in str(exc_info.value)
    assert almost not in str(exc_info.value)


def test_secrets_are_read_only() -> None:
    settings = make_settings()
    with pytest.raises(AttributeError):
        settings.jwt_secret = "x" * 40  # type: ignore[misc]


SECRET_NAME_PARTS = ("key", "secret", "password", "url", "dsn")


def test_every_secret_looking_field_is_a_secretstr() -> None:
    """By name, so a future groq_api_key-style field cannot silently be a str.

    ``dsn`` is included because the URL fields are stored as *_dsn.
    """
    plain = [
        name
        for name, field in Settings.model_fields.items()
        if any(part in name for part in SECRET_NAME_PARTS)
        and field.annotation is not SecretStr
    ]
    assert plain == []
