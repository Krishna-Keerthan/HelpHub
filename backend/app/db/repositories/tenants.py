import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant, User
from app.db.session import AsyncSessionLocal
from app.db.tenant_context import tenant_transaction


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


async def list_candidates(
    *,
    slug_regex: str,
    older_than: timedelta,
    max_users: int,
    email_suffix: str,
    limit: int = MAX_DELETE_IDS,
) -> list[TenantRef]:
    """Tenants a cleanup may remove: slug matches ``slug_regex``, created before
    ``now - older_than``, with at most ``max_users`` users, every one of whose
    emails ends with ``email_suffix``. Oldest first, at most ``limit``.

    Users are read per tenant inside a tenant transaction (users is under RLS).
    """
    pattern = re.compile(slug_regex)
    cutoff = datetime.now(UTC) - older_than
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Tenant.id, Tenant.slug)
            .where(Tenant.slug.op("~")(slug_regex), Tenant.created_at < cutoff)
            .order_by(Tenant.created_at)
        )
        found = [TenantRef(r[0], r[1]) for r in rows if pattern.search(r[1])]
    out: list[TenantRef] = []
    for ref in found:
        if len(out) >= limit:
            break
        async with tenant_transaction(ref.id) as session:
            emails = list(
                await session.scalars(select(User.email).limit(max_users + 1))
            )
        if len(emails) <= max_users and all(e.endswith(email_suffix) for e in emails):
            out.append(ref)
    return out


async def delete_by_ids(ids: Sequence[uuid.UUID]) -> int:
    """Delete exactly these tenants (cascade). Needs 1..MAX_DELETE_IDS distinct ids."""
    unique = set(ids)
    if not unique:
        raise ValueError("delete_by_ids needs at least one id")
    if len(unique) > MAX_DELETE_IDS:
        raise ValueError(f"delete_by_ids is capped at {MAX_DELETE_IDS} ids")
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(Tenant).where(Tenant.id.in_(unique)))
        await session.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]


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
