from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.deps import LLM, CurrentPrincipal, Embedder
from app.api.rate_limit import ChatLimit
from app.schemas.chat import ChatRequest
from app.services import chat as chat_service
from app.services.chat import (
    ChatContext,
    ChatEvent,
    ConversationNotFound,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    TokenEvent,
)

router = APIRouter(prefix="/chat", tags=["chat"])


# A dependency, not part of the stream: it runs before the response starts,
# so an unknown or foreign conversation is a real HTTP 404, not a 200 stream
# carrying an error event.
async def get_chat_context(
    body: ChatRequest, principal: CurrentPrincipal
) -> ChatContext:
    try:
        return await chat_service.prepare_chat(
            principal, body.conversation_id, body.message
        )
    except ConversationNotFound:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from None


PreparedChat = Annotated[ChatContext, Depends(get_chat_context)]


def _to_sse(event: ChatEvent, ctx: ChatContext) -> ServerSentEvent:
    conversation_id = str(ctx.conversation_id)
    match event:
        case SourcesEvent(sources=sources):
            return ServerSentEvent(
                event="sources",
                data={
                    "conversation_id": conversation_id,
                    "sources": [
                        {
                            "index": s.index,
                            "chunk_id": str(s.chunk_id),
                            "document_id": str(s.document_id),
                            "document_title": s.document_title,
                            "chunk_index": s.chunk_index,
                            "score": s.score,
                        }
                        for s in sources
                    ],
                },
            )
        case TokenEvent(text=text):
            return ServerSentEvent(event="token", data={"text": text})
        case DoneEvent(status=done_status, cited=cited):
            return ServerSentEvent(
                event="done",
                data={
                    "conversation_id": conversation_id,
                    "status": done_status,
                    "cited": cited,
                },
            )
        case ErrorEvent(code=code):
            return ServerSentEvent(
                event="error", data={"conversation_id": conversation_id, "code": code}
            )


# CurrentPrincipal (via get_chat_context), never CurrentUser/TenantSession:
# no connection is held while the model streams.
@router.post("/stream", response_class=EventSourceResponse, dependencies=[ChatLimit])
async def chat_stream(
    ctx: PreparedChat, embedder: Embedder, llm: LLM
) -> AsyncIterator[ServerSentEvent]:
    async for event in chat_service.stream_answer(ctx, embedder, llm):
        yield _to_sse(event, ctx)
