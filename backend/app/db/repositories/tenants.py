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


async def _passes_user_check(
    tenant_id: uuid.UUID, *, max_users: int, email_suffix: str
) -> bool:
    """1..max_users users, all with the harness email suffix. A tenant whose
    users cannot be read (none visible) fails: the check never fails open."""
    async with tenant_transaction(tenant_id) as session:
        emails = list(await session.scalars(select(User.email).limit(max_users + 1)))
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


async def delete_if_candidate(
    tenant_id: uuid.UUID,
    *,
    slug_regex: str,
    older_than: timedelta,
    max_users: int,
    email_suffix: str,
) -> int:
    """Delete one tenant only if it STILL satisfies the candidate rules (slug, age,
    users), checked immediately before the delete; returns 0 otherwise. A tenant
    that gained a real user since it was listed is therefore kept."""
    cutoff = datetime.now(UTC) - older_than
    async with AsyncSessionLocal() as session:
        slug = await session.scalar(
            select(Tenant.slug).where(
                Tenant.id == tenant_id, Tenant.created_at < cutoff
            )
        )
    if slug is None or not re.search(slug_regex, slug):
        return 0
    if not await _passes_user_check(
        tenant_id, max_users=max_users, email_suffix=email_suffix
    ):
        return 0
    return await delete_by_ids([tenant_id])


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
