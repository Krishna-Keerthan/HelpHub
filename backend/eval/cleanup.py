"""Remove leftovers of earlier evaluation runs.

Usage (from backend/):
    uv run python -m eval.cleanup          # dry run: lists candidates, deletes nothing
    uv run python -m eval.cleanup --yes    # deletes exactly the listed candidates

A candidate tenant matches ALL of: slug ``eval-<12 hex>``, created more than 10
minutes ago, at most 3 users, every user's email ending
``@eval-harness.example.com``. Deletion is by explicit id, at most 10 per run.
A stale journal (``eval/results/.eval-active.json`` of a dead pid) is cleaned
first, by its recorded ids. Refuses with ``app_env == "production"``. Holds the
shared database lock.
"""

import argparse
import asyncio
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from app.db.repositories import tenants as tenants_repo
from eval import guard, journal, lifecycle
from eval.guard import EVAL_PREFIX, GuardedEs
from eval.lock import LockHeld, hold_lock

MIN_AGE_SECONDS = 600
MAX_USERS = 3
MAX_PER_RUN = tenants_repo.MAX_DELETE_IDS
RUN_INDEX_RE = re.compile(r"^eval-[0-9a-f]{12}-")


def select_stale_indices(
    created_ms: Mapping[str, int], now_ms: int, min_age_s: int = MIN_AGE_SECONDS
) -> list[str]:
    return sorted(
        name
        for name, created in created_ms.items()
        if name.startswith(EVAL_PREFIX) and now_ms - created >= min_age_s * 1000
    )


async def eval_index_ages(es: Any) -> dict[str, int]:
    found = await es.indices.get_settings(
        index=f"{EVAL_PREFIX}*", ignore_unavailable=True, allow_no_indices=True
    )
    return {
        name: int(body["settings"]["index"]["creation_date"])
        for name, body in found.items()
    }


async def stale_run_indices(es: Any) -> list[str]:
    ages = await eval_index_ages(es)
    names = select_stale_indices(ages, int(time.time() * 1000))
    return [n for n in names if RUN_INDEX_RE.match(n)][:MAX_PER_RUN]


CRITERIA = {
    "slug_regex": journal.SLUG_RE.pattern,
    "older_than": timedelta(seconds=MIN_AGE_SECONDS),
    "max_users": MAX_USERS,
    "email_suffix": lifecycle.HARNESS_EMAIL_SUFFIX,
}


async def delete_if_still_candidate(ids: list[uuid.UUID]) -> int:
    """Re-checks the candidate rules for each id right before deleting it."""
    return sum([await tenants_repo.delete_if_candidate(i, **CRITERIA) for i in ids])  # type: ignore[arg-type]


async def candidates() -> list[tenants_repo.TenantRef]:
    return await tenants_repo.list_candidates(limit=MAX_PER_RUN, **CRITERIA)  # type: ignore[arg-type]


@dataclass
class Summary:
    tenants_removed: int = 0
    indices_removed: int = 0
    failures: list[str] = field(default_factory=list)


async def cleanup(
    es: Any,
    *,
    yes: bool,
    path: Path = journal.JOURNAL_PATH,
    delete_ids: Callable[[list[uuid.UUID]], Awaitable[int]] = delete_if_still_candidate,
) -> Summary:
    """Dry run unless ``yes``. Deletes one tenant id at a time so one failure
    does not hide the others; every failure is listed in the summary."""
    summary = Summary()
    if await lifecycle.startup_cleanup(es, path):
        print("stale journal cleaned")
    tenants = await candidates()
    indices = await stale_run_indices(es)
    verb = "delete" if yes else "would delete (dry run)"
    for ref in tenants:
        print(f"{verb} tenant {ref.id} {ref.slug}")
    for name in indices:
        print(f"{verb} index {name}")
    if not yes:
        print("dry run: nothing deleted; pass --yes to delete the lines above")
        return summary
    for ref in tenants:
        try:
            summary.tenants_removed += await delete_ids([ref.id])
        except Exception as exc:  # noqa: BLE001 - reported in the summary
            summary.failures.append(f"tenant {ref.id}: {type(exc).__name__}")
    for name in indices:
        try:
            await es.indices.delete(index=name, ignore_unavailable=True)
            summary.indices_removed += 1
        except Exception as exc:  # noqa: BLE001
            summary.failures.append(f"index {name}: {type(exc).__name__}")
    return summary


async def _main(yes: bool) -> int:
    es = GuardedEs.connect(check_run_prefix=False)
    try:
        summary = await cleanup(es, yes=yes)
    finally:
        await es.close()
    print(
        f"removed tenants: {summary.tenants_removed}  "
        f"indices: {summary.indices_removed}  failures: {len(summary.failures)}"
    )
    for failure in summary.failures:
        print(f"FAILED {failure}")
    return 3 if summary.failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--yes", action="store_true", help="delete, not just list")
    args = parser.parse_args(argv)
    try:
        guard.assert_not_production()
        with hold_lock():
            return asyncio.run(_main(args.yes))
    except guard.ProductionRefused as exc:
        print(f"refusing to run: {exc}", file=sys.stderr)
        return 2
    except LockHeld as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
