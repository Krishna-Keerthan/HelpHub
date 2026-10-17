"""Read access to the caller's own conversations and messages."""

import uuid

from app.core.principal import Principal
from app.db.models import ChatMessage, Conversation
from app.db.pagination import Page
from app.db.repositories import chat_messages as messages_repo
from app.db.repositories import conversations as conversations_repo
from app.db.tenant_context import tenant_transaction
from app.services.chat import ConversationNotFound


async def list_conversations(
    principal: Principal, *, limit: int, offset: int
) -> list[Conversation]:
    async with tenant_transaction(principal.tenant_id) as session:
        return await conversations_repo.list_for_user(
            session, principal.tenant_id, principal.user_id, limit=limit, offset=offset
        )


async def list_messages(
    principal: Principal, conversation_id: uuid.UUID, *, limit: int, offset: int
) -> list[ChatMessage]:
    async with tenant_transaction(principal.tenant_id) as session:
        conversation = await conversations_repo.get_owned(
            session, principal.tenant_id, principal.user_id, conversation_id
        )
        if conversation is None:
            raise ConversationNotFound
        return await messages_repo.list_for_conversation(
            session,
            principal.tenant_id,
            principal.user_id,
            conversation_id,
            Page(limit, offset),
        )
