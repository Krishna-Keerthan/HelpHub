"""Refuse to run tests or migrations against anything but a local database.

The message names the variable only; a URL (it carries the password) and the
host are never printed. ``python -m tests.helpers.db_guard`` is the gate's check.
"""

import sys
from urllib.parse import urlsplit

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db", "postgres"})


def host_is_local(url: str | None) -> bool:
    if not url:
        return False
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in LOCAL_HOSTS


def classify(url: str | None) -> str:
    """local, hosted (supabase or pooler host), other, or unset. Never returns the URL."""
    if not url:
        return "unset"
    if host_is_local(url):
        return "local"
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        host = ""
    return "hosted" if "supabase" in host or "pooler" in host else "other"


def non_local_variables(urls: dict[str, str | None]) -> list[str]:
    """Names of the variables whose host is not local (or that are unset)."""
    return [name for name, url in urls.items() if not host_is_local(url)]


def refusal_message(names: list[str]) -> str | None:
    if not names:
        return None
    return (
        f"refusing to run: {', '.join(names)} not local "
        "(host must be localhost, 127.0.0.1, ::1, db or postgres)"
    )


def load_urls() -> tuple[dict[str, str | None] | None, str | None]:
    """(resolved database URLs, None), or (None, exception class name) if settings fail.

    Only the class name is kept: the exception text may contain a URL.
    """
    try:
        from app.core.config import settings

        migration = settings.migration_database_dsn
        return (
            {
                "DATABASE_URL": settings.database_dsn.get_secret_value(),
                "MIGRATION_DATABASE_URL": (
                    migration.get_secret_value() if migration else None
                ),
            },
            None,
        )
    except Exception as exc:  # noqa: BLE001 (class name only)
        return None, type(exc).__name__


def current_refusal() -> str | None:
    urls, error = load_urls()
    if urls is None:
        return (
            f"refusing to run: settings failed to load ({error}); "
            "DATABASE_URL and MIGRATION_DATABASE_URL could not be checked"
        )
    return refusal_message(non_local_variables(urls))


if __name__ == "__main__":
    message = current_refusal()
    if message:
        print(message, file=sys.stderr)
        sys.exit(3)
