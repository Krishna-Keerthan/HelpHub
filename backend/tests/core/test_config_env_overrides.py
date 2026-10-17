"""Render-class overrides are plain environment variables (docs/deploy/runbook.md)."""

import pytest

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
