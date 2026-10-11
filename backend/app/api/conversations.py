import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentPrincipal
from app.schemas.chat import ChatMessageRead, ConversationRead
from app.services import conversations as conversations_service
from app.services.chat import ConversationNotFound

router = APIRouter(prefix="/conversations", tags=["chat"])


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationRead]:
    rows = await conversations_service.list_conversations(
        principal, limit=limit, offset=offset
    )
    return [ConversationRead.model_validate(row) for row in rows]


@router.get("/{conversation_id}/messages", response_model=list[ChatMessageRead])
async def list_messages(
    conversation_id: uuid.UUID,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ChatMessageRead]:
    try:
        rows = await conversations_service.list_messages(
            principal, conversation_id, limit=limit, offset=offset
        )
    except ConversationNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from None
    return [ChatMessageRead.model_validate(row) for row in rows]
