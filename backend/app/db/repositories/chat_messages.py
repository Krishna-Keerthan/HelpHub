import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage


async def add(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    role: str,
    content: str,
    status: str,
    sources: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> ChatMessage:
    message = ChatMessage(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        status=status,
        sources=sources or [],
        model=model,
    )
    session.add(message)
    await session.flush()
    return message


async def recent_history(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int,
) -> list[ChatMessage]:
    """The last ``limit`` useful messages, oldest first.

    User messages, and assistant messages that completed: a refusal, failure
    or interrupted partial is not worth feeding back to the model.
    """
    result = await session.execute(
        select(ChatMessage)
        .where(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.conversation_id == conversation_id,
            or_(ChatMessage.role == "user", ChatMessage.status == "complete"),
        )
        .order_by(ChatMessage.seq.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def list_for_conversation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage)
        .where(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.conversation_id == conversation_id,
        )
        .order_by(ChatMessage.seq)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars())
