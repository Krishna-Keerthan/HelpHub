import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation


class ConversationNotOwned(Exception):
    """The conversation is unknown, or belongs to another user or tenant."""


async def create(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation:
    conversation = Conversation(tenant_id=tenant_id, user_id=user_id)
    session.add(conversation)
    await session.flush()
    return conversation


async def get_owned(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> Conversation | None:
    """The user's own conversation; another user's (same tenant) is None."""
    result = await session.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
            Conversation.id == conversation_id,
        )
    )
    return result.scalar_one_or_none()


async def touch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> int:
    """Bump updated_at on the user's own conversation; returns rows affected."""
    result = await session.execute(
        update(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
            Conversation.id == conversation_id,
        )
        .values(updated_at=func.now())
    )
    return result.rowcount  # type: ignore[attr-defined]


async def list_for_user(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.tenant_id == tenant_id, Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())
