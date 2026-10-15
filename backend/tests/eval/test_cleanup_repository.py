"""Id-based tenant cleanup functions in repositories/tenants.py (real database)."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
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
        (None, [], 60),  # no users at all: never fails open
    ],
)
async def test_non_matching_tenants_are_never_candidates(
    make: Make, slug: str | None, emails: list[str], age: int
) -> None:
    tid = await make(slug or _slug(), emails, age)
    assert tid not in {c.id for c in await _list()}


async def test_limit_caps_the_candidate_list(make: Make) -> None:
    for _ in range(3):
        await make(_slug(), [f"a{SUFFIX}"])
    assert len(await _list(limit=2)) <= 2


CRITERIA = {
    "slug_regex": SLUG_RE,
    "older_than": timedelta(minutes=10),
    "max_users": 3,
    "email_suffix": SUFFIX,
}


async def test_delete_if_candidate_deletes_a_current_candidate(make: Make) -> None:
    tid = await make(_slug(), [f"admin{SUFFIX}"])
    assert await tenants_repo.delete_if_candidate(tid, **CRITERIA) == 1  # type: ignore[arg-type]
    assert await tenants_repo.existing_ids([tid]) == set()


async def test_delete_if_candidate_keeps_a_tenant_that_stopped_matching(
    make: Make, owner_conn: AsyncConnection
) -> None:
    tid = await make(_slug(), [f"admin{SUFFIX}"])
    assert tid in {c.id for c in await _list()}  # listed ...
    await owner_conn.execute(  # ... then a real user appears
        text(
            "INSERT INTO users (tenant_id, email, password_hash, role, is_active) "
            "VALUES (:t, 'real@acme.example.com', 'x', 'admin', true)"
        ),
        {"t": tid},
    )
    await owner_conn.commit()
    assert await tenants_repo.delete_if_candidate(tid, **CRITERIA) == 0  # type: ignore[arg-type]
    assert await tenants_repo.existing_ids([tid]) == {tid}


@pytest.mark.parametrize(
    ("slug", "emails", "age"),
    [
        ("eval-corp", [f"admin{SUFFIX}"], 60),
        (None, [], 60),
        (None, [f"admin{SUFFIX}"], 1),
    ],
)
async def test_delete_if_candidate_refuses_non_candidates(
    make: Make, slug: str | None, emails: list[str], age: int
) -> None:
    tid = await make(slug or _slug(), emails, age)
    assert await tenants_repo.delete_if_candidate(tid, **CRITERIA) == 0  # type: ignore[arg-type]
    assert await tenants_repo.existing_ids([tid]) == {tid}


async def test_delete_if_candidate_accepts_zero_min_age(make: Make) -> None:
    tid = await make(_slug(), [f"admin{SUFFIX}"], age_minutes=0)
    zero = {**CRITERIA, "older_than": timedelta(0)}
    assert await tenants_repo.delete_if_candidate(tid, **zero) == 1  # type: ignore[arg-type]
    assert await tenants_repo.existing_ids([tid]) == set()


# --- races with a concurrent user insert (two real connections) -------------------

STEP = 15  # seconds: every await in a race test is bounded


@pytest.fixture
async def monitor() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            yield conn
    finally:
        await engine.dispose()


async def _wait_until_a_delete_is_blocked(monitor: AsyncConnection) -> None:
    """Poll pg_stat_activity until a runtime-role backend waits on a lock."""
    sql = text(
        "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
        "AND application_name LIKE 'helphub-%'"
    )
    for _ in range(300):
        if (await monitor.execute(sql)).scalar_one():
            return
        await monitor.rollback()
        await asyncio.sleep(0.05)
    raise AssertionError("delete_if_candidate never blocked on the tenant row")


INSERT_REAL_USER = text(
    "INSERT INTO users (tenant_id, email, password_hash, role, is_active) "
    "VALUES (:t, 'real@acme.example.com', 'x', 'admin', true)"
)


async def test_race_user_insert_held_open_wins_over_the_delete(
    make: Make, owner_conn: AsyncConnection, monitor: AsyncConnection
) -> None:
    """Order A: the insert is in flight, the delete must wait for it, then see the
    real user and refuse. Tenant and user both survive."""
    tid = await make(_slug(), [f"admin{SUFFIX}"])
    inserted, release = asyncio.Event(), asyncio.Event()

    async def inserter() -> None:
        await owner_conn.execute(INSERT_REAL_USER, {"t": tid})  # uncommitted
        inserted.set()
        await asyncio.wait_for(release.wait(), STEP)
        await owner_conn.commit()

    ins = asyncio.create_task(inserter())
    await asyncio.wait_for(inserted.wait(), STEP)
    dele = asyncio.create_task(tenants_repo.delete_if_candidate(tid, **CRITERIA))  # type: ignore[arg-type]
    await asyncio.wait_for(_wait_until_a_delete_is_blocked(monitor), STEP)
    assert not dele.done()
    release.set()
    await asyncio.wait_for(ins, STEP)
    assert await asyncio.wait_for(dele, STEP) == 0
    assert await tenants_repo.existing_ids([tid]) == {tid}
    users = await owner_conn.scalar(
        text("SELECT count(*) FROM users WHERE tenant_id = :t"), {"t": tid}
    )
    assert users == 2


async def test_race_delete_committed_first_makes_the_insert_fail(
    make: Make, owner_conn: AsyncConnection
) -> None:
    """Order B: the delete commits first; the later insert is rejected by the
    foreign key (23503) and leaves no orphan user."""
    tid = await make(_slug(), [f"admin{SUFFIX}"])
    deleted = asyncio.Event()

    async def deleter() -> int:
        n = await tenants_repo.delete_if_candidate(tid, **CRITERIA)  # type: ignore[arg-type]
        deleted.set()
        return n

    await owner_conn.execute(text("SELECT 1"))  # a transaction is already open
    dele = asyncio.create_task(deleter())
    await asyncio.wait_for(deleted.wait(), STEP)
    assert await dele == 1
    with pytest.raises(DBAPIError) as caught:
        await asyncio.wait_for(owner_conn.execute(INSERT_REAL_USER, {"t": tid}), STEP)
    orig = caught.value.orig
    code = getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )
    assert code == "23503"
    await owner_conn.rollback()
    orphans = await owner_conn.scalar(
        text("SELECT count(*) FROM users WHERE tenant_id = :t"), {"t": tid}
    )
    assert orphans == 0


async def test_lock_timeout_skips_instead_of_hanging(
    make: Make, owner_conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = await make(_slug(), [f"admin{SUFFIX}"])
    monkeypatch.setattr(tenants_repo, "LOCK_TIMEOUT_MS", 200)
    await owner_conn.execute(  # another transaction holds the tenant row
        text("SELECT id FROM tenants WHERE id = :t FOR UPDATE"), {"t": tid}
    )
    result = await asyncio.wait_for(
        tenants_repo.delete_if_candidate(tid, **CRITERIA),  # type: ignore[arg-type]
        STEP,
    )
    assert result == 0
    await owner_conn.rollback()
    assert await tenants_repo.existing_ids([tid]) == {tid}
