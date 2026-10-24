"""Print where DATABASE_URL and MIGRATION_DATABASE_URL point, never the URLs.

Four lines, "<VAR> (<source>): <local|hosted|other|unset|error>", first as seen in the
process environment, then as resolved from .env alone (the two variables are
removed from the environment before settings load). "error" means Settings() failed
to load (the exception class goes to stderr, never its text). Exits 1 if any line is
hosted, other or error. No database connection is made.

Run from backend/:  uv run python scripts/check_local_db.py
"""

import os
import sys

from tests.helpers.db_guard import classify, load_urls

VARIABLES = ("DATABASE_URL", "MIGRATION_DATABASE_URL")


def render(
    environment: dict[str, str | None],
    dotenv: dict[str, str | None] | None,
) -> list[str]:
    """``dotenv`` is None when settings failed to load: both .env lines say error."""
    lines = [
        f"{name} (environment): {classify(environment.get(name))}" for name in VARIABLES
    ]
    lines += [
        f"{name} (.env only): "
        f"{'error' if dotenv is None else classify(dotenv.get(name))}"
        for name in VARIABLES
    ]
    return lines


def ok(lines: list[str]) -> bool:
    return not any(line.endswith((": hosted", ": other", ": error")) for line in lines)


def dotenv_urls() -> tuple[dict[str, str | None] | None, str | None]:
    for name in VARIABLES:
        os.environ.pop(name, None)
    return load_urls()


def main() -> int:
    environment = {name: os.environ.get(name) for name in VARIABLES}
    dotenv, error = dotenv_urls()
    lines = render(environment, dotenv)
    print("\n".join(lines))
    if error:
        print(f"settings failed to load: {error}", file=sys.stderr)
    return 0 if ok(lines) else 1


if __name__ == "__main__":
    sys.exit(main())
