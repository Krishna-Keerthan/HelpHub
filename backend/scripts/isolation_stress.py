"""Concurrent tenant-isolation stress run against the LOCAL database. Not a pytest test.

Runtime role (helphub_app), small pool, many concurrent tasks. Each task runs a random
mix of five operations, each in its own transaction:
  read-own      tenant sees only its own rows
  x-insert      insert a row for another tenant: must raise the RLS error (SQLSTATE 42501)
  x-update      update another tenant's row: must affect 0 rows
  x-delete      delete another tenant's row: must affect 0 rows
  read-no-ctx   no tenant set, on a pooled (reused) connection: must see 0 rows
Anything else counts as a leak. Unexpected errors are counted separately and also fail.

Default mode uses the real ``documents`` table (rows live under tenants whose slug starts
``stress-``; they are deleted before and after the run through the owner role).
``--control`` runs the same workload on a scratch table with NO row level security,
created and dropped here; it must report leaks > 0, which proves the checks can detect
a leak. In control mode the exit code is 0 when leaks > 0 and 1 when none were found.

Refuses to run unless DATABASE_URL and MIGRATION_DATABASE_URL both point at a local host.
Never prints a URL, a password or an exception message.

Run from backend/:  uv run python scripts/isolation_stress.py [--control]
"""

import argparse
import asyncio
import random
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.tenant_context import set_tenant
from tests.helpers.db_guard import current_refusal

SLUG_PREFIX = "stress-"
CONTROL_TABLE = "stress_control_docs"
REAL_TABLE = "documents"
DOCS_PER_TENANT = 3
RLS_VIOLATION = "42501"
OPS = ("read_own", "x_insert", "x_update", "x_delete", "read_no_ctx")


@dataclass
class Stats:
    transactions: int = 0
    reads_checked: int = 0
    writes_attempted: int = 0
    writes_blocked: int = 0
    leaks: int = 0
    errors: Counter[str] = field(default_factory=Counter)


def sqlstate(exc: DBAPIError) -> str | None:
    orig = exc.orig
    for source in (orig, getattr(orig, "__cause__", None)):
        code = getattr(source, "sqlstate", None) or getattr(source, "pgcode", None)
        if code:
            return str(code)
    return None


def is_rls_violation(exc: DBAPIError) -> bool:
    # Message is inspected, never printed.
    return sqlstate(exc) == RLS_VIOLATION and "row-level security" in str(exc.orig)


async def seed_real(
    maker: async_sessionmaker[AsyncSession], tenants: int
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Create tenants and their documents through the runtime role."""
    run = uuid.uuid4().hex[:8]
    rows: dict[uuid.UUID, list[uuid.UUID]] = {}
    for index in range(tenants):
        async with maker() as session:
            tenant_id = (
                await session.execute(
                    text(
                        "INSERT INTO tenants (name, slug) VALUES (:n, :s) RETURNING id"
                    ),
                    {"n": f"stress {index}", "s": f"{SLUG_PREFIX}{run}-{index}"},
                )
            ).scalar_one()
            await session.commit()
        rows[tenant_id] = await seed_documents(maker, REAL_TABLE, tenant_id)
    return rows


async def seed_documents(
    maker: async_sessionmaker[AsyncSession], table: str, tenant_id: uuid.UUID
) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    async with maker() as session:
        await set_tenant(session, tenant_id)
        for index in range(DOCS_PER_TENANT):
            ids.append(
                (
                    await session.execute(
                        text(
                            f"INSERT INTO {table} (tenant_id, title, raw_text, content_hash) "
                            "VALUES (:t, :title, 'x', :h) RETURNING id"
                        ),
                        {
                            "t": tenant_id,
                            "title": f"doc-{index}",
                            "h": uuid.uuid4().hex * 2,
                        },
                    )
                ).scalar_one()
            )
        await session.commit()
    return ids


async def run_op(
    op: str,
    maker: async_sessionmaker[AsyncSession],
    table: str,
    me: uuid.UUID,
    victims: dict[uuid.UUID, list[uuid.UUID]],
    rng: random.Random,
    stats: Stats,
) -> None:
    others = [t for t in victims if t != me]
    other = rng.choice(others)
    victim = rng.choice(victims[other])
    async with maker() as session:
        stats.transactions += 1
        try:
            if op != "read_no_ctx":
                await set_tenant(session, me)
            if op == "read_own":
                rows = (
                    await session.execute(text(f"SELECT tenant_id FROM {table}"))
                ).all()
                stats.reads_checked += 1
                if len(rows) != DOCS_PER_TENANT or any(r[0] != me for r in rows):
                    stats.leaks += 1
            elif op == "read_no_ctx":
                count = (
                    await session.execute(text(f"SELECT count(*) FROM {table}"))
                ).scalar_one()
                stats.reads_checked += 1
                if count != 0:
                    stats.leaks += 1
            elif op == "x_insert":
                stats.writes_attempted += 1
                await session.execute(
                    text(
                        f"INSERT INTO {table} (tenant_id, title, raw_text, content_hash) "
                        "VALUES (:t, 'intruder', 'x', :h)"
                    ),
                    {"t": other, "h": uuid.uuid4().hex * 2},
                )
                stats.leaks += 1  # the insert was accepted
            else:
                stats.writes_attempted += 1
                sql = (
                    f"UPDATE {table} SET title = title WHERE id = :id"
                    if op == "x_update"
                    else f"DELETE FROM {table} WHERE id = :id"
                )
                result = await session.execute(text(sql), {"id": victim})
                if result.rowcount == 0:  # type: ignore[attr-defined]
                    stats.writes_blocked += 1
                else:
                    stats.leaks += 1
            await session.rollback()
        except DBAPIError as exc:
            await session.rollback()
            if op == "x_insert" and is_rls_violation(exc):
                stats.writes_blocked += 1
            else:
                stats.errors[f"{op}/{type(exc.orig).__name__}/{sqlstate(exc)}"] += 1


async def task(
    maker: async_sessionmaker[AsyncSession],
    gate: asyncio.Semaphore,
    table: str,
    victims: dict[uuid.UUID, list[uuid.UUID]],
    ops_per_task: int,
    seed: int,
    stats: Stats,
) -> None:
    rng = random.Random(seed)
    async with gate:
        me = rng.choice(list(victims))
        for _ in range(ops_per_task):
            await run_op(rng.choice(OPS), maker, table, me, victims, rng, stats)


async def owner_exec(statements: list[str]) -> None:
    dsn = settings.migration_database_url
    engine = create_async_engine(dsn, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def main_async(args: argparse.Namespace) -> int:
    clean = [f"DELETE FROM tenants WHERE slug LIKE '{SLUG_PREFIX}%'"]
    engine = create_async_engine(
        settings.database_url,
        pool_size=args.pool_size,
        max_overflow=0,
        pool_timeout=120,
        hide_parameters=True,
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    table = CONTROL_TABLE if args.control else REAL_TABLE
    stats = Stats()
    try:
        async with maker() as session:
            role = (await session.execute(text("SELECT current_user"))).scalar_one()
        if role != "helphub_app":
            print(f"refusing to run: connected as {role}, expected helphub_app")
            return 2
        if args.control:
            await owner_exec(
                [
                    f"DROP TABLE IF EXISTS {CONTROL_TABLE}",
                    (
                        f"CREATE TABLE {CONTROL_TABLE} (id uuid PRIMARY KEY DEFAULT "
                        "gen_random_uuid(), tenant_id uuid NOT NULL, title text NOT NULL, "
                        "raw_text text NOT NULL, content_hash text NOT NULL)"
                    ),
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON {CONTROL_TABLE} TO helphub_app",
                ]
            )
            victims = {}
            for _ in range(args.tenants):
                tenant_id = uuid.uuid4()
                victims[tenant_id] = await seed_documents(maker, table, tenant_id)
        else:
            await owner_exec(clean)
            victims = await seed_real(maker, args.tenants)

        base = random.Random(args.seed)
        gate = asyncio.Semaphore(args.concurrency)
        await asyncio.gather(
            *(
                task(
                    maker,
                    gate,
                    table,
                    victims,
                    args.ops_per_task,
                    base.getrandbits(32),
                    stats,
                )
                for _ in range(args.tasks)
            )
        )
    finally:
        await engine.dispose()
        await owner_exec([f"DROP TABLE IF EXISTS {CONTROL_TABLE}"] + clean)

    print(
        f"mode={'control-no-rls' if args.control else 'rls'} role={role} "
        f"pool={args.pool_size} tasks={args.tasks} in_flight={args.concurrency} "
        f"seed={args.seed} tenants={args.tenants} transactions={stats.transactions} "
        f"reads_checked={stats.reads_checked} writes_attempted={stats.writes_attempted} "
        f"writes_blocked={stats.writes_blocked} leaks={stats.leaks} "
        f"errors={sum(stats.errors.values())}"
    )
    if stats.errors:
        print(f"error kinds: {dict(stats.errors)}")
    if args.control:
        return 0 if stats.leaks > 0 and not stats.errors else 1
    return 1 if stats.leaks or stats.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenants", type=int, default=10)
    parser.add_argument("--tasks", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--pool-size", type=int, default=5)
    parser.add_argument("--ops-per-task", type=int, default=5)
    parser.add_argument(
        "--seed", type=int, default=random.SystemRandom().getrandbits(32)
    )
    parser.add_argument(
        "--control", action="store_true", help="same workload on a table without RLS"
    )
    args = parser.parse_args(argv)
    if args.tenants < 2:
        parser.error("--tenants must be at least 2")
    refusal = current_refusal()
    if refusal:
        print(refusal, file=sys.stderr)
        return 3
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
