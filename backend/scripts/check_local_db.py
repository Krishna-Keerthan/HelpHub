"""Print where DATABASE_URL and MIGRATION_DATABASE_URL point, never the URLs.

Four lines, "<VAR> (<source>): <local|hosted|other|unset>", first as seen in the
process environment, then as resolved from .env alone (the two variables are
removed from the environment before settings load). Exits 1 if any line is
hosted or other. No database connection is made.

Run from backend/:  uv run python scripts/check_local_db.py
"""

import os
import sys

from tests.helpers.db_guard import classify

VARIABLES = ("DATABASE_URL", "MIGRATION_DATABASE_URL")


def render(
    environment: dict[str, str | None], dotenv: dict[str, str | None]
) -> list[str]:
    lines = []
    for source, urls in (("environment", environment), (".env only", dotenv)):
        lines += [
            f"{name} ({source}): {classify(urls.get(name))}" for name in VARIABLES
        ]
    return lines


def ok(lines: list[str]) -> bool:
    return not any(line.endswith((": hosted", ": other")) for line in lines)


def dotenv_urls() -> dict[str, str | None]:
    for name in VARIABLES:
        os.environ.pop(name, None)
    try:
        from app.core.config import settings

        migration = settings.migration_database_dsn
        return {
            "DATABASE_URL": settings.database_dsn.get_secret_value(),
            "MIGRATION_DATABASE_URL": migration.get_secret_value()
            if migration
            else None,
        }
    except Exception:  # noqa: BLE001 (class name only: the message could carry a URL)
        return {}


def main() -> int:
    environment = {name: os.environ.get(name) for name in VARIABLES}
    lines = render(environment, dotenv_urls())
    print("\n".join(lines))
    return 0 if ok(lines) else 1


if __name__ == "__main__":
    sys.exit(main())
