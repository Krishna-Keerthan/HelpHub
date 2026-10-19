"""Render-class overrides are plain environment variables (docs/deploy/runbook.md)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {
    "database_url": "postgresql+asyncpg://x:y@localhost/db",
    "migration_database_url": "postgresql+asyncpg://x:y@localhost/db",
    "jwt_secret": "k" * 40,
}


def test_pdf_limits_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PDF_TIMEOUT_SECONDS", "PDF_CPU_SECONDS", "PDF_MAX_CONCURRENCY"):
        monkeypatch.delenv(name, raising=False)
    defaults = Settings(_env_file=None, **BASE)  # type: ignore[arg-type]
    assert (defaults.pdf_timeout_seconds, defaults.pdf_cpu_seconds) == (10.0, 10)
    assert defaults.pdf_max_concurrency == 2

    monkeypatch.setenv("PDF_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("PDF_MAX_CONCURRENCY", "1")
    overridden = Settings(_env_file=None, **BASE)  # type: ignore[arg-type]
    assert overridden.pdf_timeout_seconds == 120.0
    assert overridden.pdf_max_concurrency == 1
    assert overridden.pdf_cpu_seconds == 10  # not overridden: the CPU limit stays


def test_ready_timeout_defaults_to_five_seconds_and_is_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("READY_TIMEOUT_SECONDS", raising=False)
    assert Settings(_env_file=None, **BASE).ready_timeout_seconds == 5.0  # type: ignore[arg-type]

    monkeypatch.setenv("READY_TIMEOUT_SECONDS", "20")
    assert Settings(_env_file=None, **BASE).ready_timeout_seconds == 20.0  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["0", "-1"])
def test_ready_timeout_must_be_positive(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("READY_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE)  # type: ignore[arg-type]


def test_embedding_threads_unset_by_default_and_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EMBEDDING_THREADS", raising=False)
    assert Settings(_env_file=None, **BASE).embedding_threads is None  # type: ignore[arg-type]

    monkeypatch.setenv("EMBEDDING_THREADS", "1")
    assert Settings(_env_file=None, **BASE).embedding_threads == 1  # type: ignore[arg-type]

    monkeypatch.setenv("EMBEDDING_THREADS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE)  # type: ignore[arg-type]
