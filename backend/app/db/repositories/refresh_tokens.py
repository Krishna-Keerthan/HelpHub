import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RefreshToken


async def add(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    jti: uuid.UUID,
    family_id: uuid.UUID,
    expires_at: datetime,
) -> None:
    session.add(
        RefreshToken(
            jti=jti,
            tenant_id=tenant_id,
            user_id=user_id,
            family_id=family_id,
            expires_at=expires_at,
        )
    )
    await session.flush()


async def get_for_update(
    session: AsyncSession, tenant_id: uuid.UUID, jti: uuid.UUID
) -> RefreshToken | None:
    """The row, locked until the transaction ends: two uses of one token serialise."""
    result = await session.execute(
        select(RefreshToken)
        .where(RefreshToken.tenant_id == tenant_id, RefreshToken.jti == jti)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def mark_used(
    session: AsyncSession, tenant_id: uuid.UUID, jti: uuid.UUID
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.tenant_id == tenant_id, RefreshToken.jti == jti)
        .values(used_at=func.now())
    )


async def revoke_family(
    session: AsyncSession, tenant_id: uuid.UUID, family_id: uuid.UUID
) -> int:
    """Revoke every not-yet-revoked token of the family; returns rows changed."""
    result = await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.tenant_id == tenant_id,
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    return result.rowcount  # type: ignore[attr-defined]


async def delete_expired(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    result = await session.execute(
        delete(RefreshToken).where(
            RefreshToken.tenant_id == tenant_id, RefreshToken.expires_at < func.now()
        )
    )
    return result.rowcount  # type: ignore[attr-defined]
