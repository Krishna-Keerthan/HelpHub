"""Id-based tenant cleanup functions in repositories/tenants.py (real database)."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

import pytest

from app.db.repositories import tenants as tenants_repo

SLUG_RE = r"^eval-[0-9a-f]{12}$"
SUFFIX = "@eval-harness.example.com"
Make = Callable[..., Awaitable[uuid.UUID]]  # the conftest ``make`` fixture


def _list(**over: object) -> Awaitable[list[tenants_repo.TenantRef]]:
    args: dict[str, object] = {
        "slug_regex": SLUG_RE,
        "older_than": timedelta(minutes=10),
        "max_users": 3,
        "email_suffix": SUFFIX,
    }
    args.update(over)
    return tenants_repo.list_candidates(**args)  # type: ignore[arg-type]


def _slug() -> str:
    return f"eval-{uuid.uuid4().hex[:12]}"


async def test_matching_tenant_is_a_candidate(make: Make) -> None:
    tid = await make(_slug(), [f"admin{SUFFIX}"])
    assert tid in {c.id for c in await _list()}


@pytest.mark.parametrize(
    ("slug", "emails", "age"),
    [
        ("eval-corp", [f"admin{SUFFIX}"], 60),  # slug shape
        (None, ["admin@acme.example.com"], 60),  # normal user
        (None, [f"admin{SUFFIX}", "x@acme.example.com"], 60),  # one foreign user
        (None, [f"{i}{SUFFIX}" for i in range(4)], 60),  # too many users
        (None, [f"admin{SUFFIX}"], 2),  # too young
    ],
)
async def test_non_matching_tenants_are_never_candidates(
    make: Make, slug: str | None, emails: list[str], age: int
) -> None:
    tid = await make(slug or _slug(), emails, age)
    assert tid not in {c.id for c in await _list()}


async def test_delete_by_ids_removes_exactly_those(make: Make) -> None:
    a = await make(_slug(), [f"a{SUFFIX}"])
    b = await make(_slug(), [f"b{SUFFIX}"])
    assert await tenants_repo.delete_by_ids([a]) == 1
    assert await tenants_repo.existing_ids([a, b]) == {b}


async def test_delete_by_ids_rejects_empty_and_oversized() -> None:
    with pytest.raises(ValueError):
        await tenants_repo.delete_by_ids([])
    with pytest.raises(ValueError):
        await tenants_repo.delete_by_ids([uuid.uuid4() for _ in range(11)])


async def test_limit_caps_the_candidate_list(make: Make) -> None:
    for _ in range(3):
        await make(_slug(), [f"a{SUFFIX}"])
    assert len(await _list(limit=2)) <= 2
