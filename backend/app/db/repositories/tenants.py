import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant, User
from app.db.session import AsyncSessionLocal
from app.db.tenant_context import set_tenant, tenant_transaction

logger = logging.getLogger(__name__)
LOCK_NOT_AVAILABLE = "55P03"
LOCK_TIMEOUT_MS = 5000


async def get_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


async def create(session: AsyncSession, *, name: str, slug: str) -> Tenant:
    tenant = Tenant(name=name, slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


async def list_ids() -> list[uuid.UUID]:
    """Every tenant id (maintenance scripts). Own session: the tenants table
    is not tenant-scoped."""
    async with AsyncSessionLocal() as session:
        result = await session.scalars(select(Tenant.id).order_by(Tenant.created_at))
        return list(result)


MAX_DELETE_IDS = 10


@dataclass(frozen=True)
class TenantRef:
    id: uuid.UUID
    slug: str


async def _passes_user_check(
    tenant_id: uuid.UUID, *, max_users: int, email_suffix: str
) -> bool:
    """1..max_users users, all with the harness email suffix. A tenant whose
    users cannot be read (none visible) fails: the check never fails open."""
    async with tenant_transaction(tenant_id) as session:
        emails = list(
            await session.scalars(
                select(User.email)
                .where(User.tenant_id == tenant_id)
                .limit(max_users + 1)
            )
        )
    return 1 <= len(emails) <= max_users and all(
        e.lower().endswith(email_suffix.lower()) for e in emails
    )


async def list_candidates(
    *,
    slug_regex: str,
    older_than: timedelta,
    max_users: int,
    email_suffix: str,
    limit: int = MAX_DELETE_IDS,
    scan_limit: int = 200,
) -> list[TenantRef]:
    """Tenants a cleanup may remove: slug matches ``slug_regex``, created before
    ``now - older_than``, with 1..``max_users`` users, every one of whose emails
    ends with ``email_suffix``. Oldest first, at most ``limit``; at most
    ``scan_limit`` slug matches are examined.

    Users are read per tenant inside a tenant transaction (users is under RLS).
    """
    pattern = re.compile(slug_regex)
    cutoff = datetime.now(UTC) - older_than
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Tenant.id, Tenant.slug)
            .where(Tenant.slug.op("~")(slug_regex), Tenant.created_at < cutoff)
            .order_by(Tenant.created_at)
            .limit(scan_limit)
        )
        found = [TenantRef(r[0], r[1]) for r in rows if pattern.search(r[1])]
    out: list[TenantRef] = []
    for ref in found:
        if len(out) >= limit:
            break
        if await _passes_user_check(
            ref.id, max_users=max_users, email_suffix=email_suffix
        ):
            out.append(ref)
    return out


def _sqlstate(exc: DBAPIError) -> str | None:
    orig = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )


async def delete_if_candidate(
    tenant_id: uuid.UUID,
    *,
    slug_regex: str,
    older_than: timedelta,
    max_users: int,
    email_suffix: str,
) -> int:
    """Delete one tenant only if it satisfies the candidate rules (slug, age,
    users); returns 0 otherwise. This is the only function that deletes tenants.

    One transaction: the tenant row is locked ``FOR UPDATE`` first, so a user
    insert (which takes a ``FOR KEY SHARE`` lock on the tenant through its
    foreign key) either committed before the lock and is seen by the re-check,
    or waits until this transaction ends and then fails with 23503. A lock that
    cannot be had within ``LOCK_TIMEOUT_MS`` skips the tenant (returns 0).
    """
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text(f"SET LOCAL lock_timeout = '{int(LOCK_TIMEOUT_MS)}ms'")
            )
            row = (
                await session.execute(
                    select(Tenant.slug, Tenant.created_at, func.now())
                    .where(Tenant.id == tenant_id)
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                return 0
            slug, created_at, now = row
            if not re.search(slug_regex, slug) or created_at >= now - older_than:
                return 0
            await set_tenant(session, tenant_id)
            emails = list(
                await session.scalars(
                    select(User.email)
                    .where(User.tenant_id == tenant_id)
                    .limit(max_users + 1)
                )
            )
            if not (1 <= len(emails) <= max_users) or not all(
                e.lower().endswith(email_suffix.lower()) for e in emails
            ):
                return 0
            result = await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()
            return int(result.rowcount)  # type: ignore[attr-defined]
        except DBAPIError as exc:
            if _sqlstate(exc) != LOCK_NOT_AVAILABLE:
                raise
            logger.warning(
                "tenant delete skipped: tenant=%s sqlstate=%s",
                tenant_id,
                LOCK_NOT_AVAILABLE,
            )
            return 0
        finally:
            await session.rollback()  # no-op after commit; ends a skipped transaction


async def existing_ids(ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
    """Which of ``ids`` still exist (verifies a cleanup)."""
    if not ids:
        return set()
    async with AsyncSessionLocal() as session:
        result = await session.scalars(select(Tenant.id).where(Tenant.id.in_(set(ids))))
        return set(result)


async def id_for_slug(slug: str) -> uuid.UUID | None:
    async with AsyncSessionLocal() as session:
        tenant = await get_by_slug(session, slug)
        return None if tenant is None else tenant.id


async def count_slug_prefix(prefix: str) -> int:
    """How many tenants have a slug starting with ``prefix`` (informational)."""
    async with AsyncSessionLocal() as session:
        rows = await session.scalars(
            select(Tenant.id).where(Tenant.slug.startswith(prefix, autoescape=True))
        )
        return len(list(rows))
