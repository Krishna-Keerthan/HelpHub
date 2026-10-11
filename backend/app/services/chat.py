"""Grounded chat orchestration, as a stream of typed events.

Transactions are short and never span a slow call: the conversation and user
message are written first (``prepare_chat``), the query is embedded with no
transaction open, retrieval gets its own transaction, tokens stream with no
transaction open, and the assistant message is saved in a final transaction.

A client disconnect surfaces as CancelledError or GeneratorExit at a yield;
the ``finally`` then saves whatever was streamed as ``interrupted`` (shielded,
so a cancelled task still completes the write).
"""

import asyncio
import logging
import traceback
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.principal import Principal
from app.db.repositories import chat_messages as messages_repo
from app.db.repositories import conversations as conversations_repo
from app.db.repositories import documents as documents_repo
from app.db.tenant_context import tenant_transaction
from app.services.documents import sqlstate_of
from app.services.embeddings import EmbeddingProvider
from app.services.llm import LLMError, LLMProvider, Message
from app.services.prompts import PromptSource, build_messages, parse_citations
from app.services.search import search_in_session

logger = logging.getLogger(__name__)

# Never model output and never contains user input.
REFUSAL_TEXT = (
    "I couldn't find anything in your knowledge base that answers this question."
)
INTERNAL_ERROR = "internal_error"


class ConversationNotFound(Exception):
    """Unknown, or not the caller's (same tenant, other user, or other tenant)."""


@dataclass(frozen=True)
class SourceInfo:
    index: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    score: float


@dataclass(frozen=True)
class SourcesEvent:
    sources: list[SourceInfo]


@dataclass(frozen=True)
class TokenEvent:
    text: str


@dataclass(frozen=True)
class DoneEvent:
    status: str
    cited: list[int]


@dataclass(frozen=True)
class ErrorEvent:
    code: str


ChatEvent = SourcesEvent | TokenEvent | DoneEvent | ErrorEvent


@dataclass(frozen=True)
class ChatContext:
    principal: Principal
    conversation_id: uuid.UUID
    question: str
    history: list[Message]


async def prepare_chat(
    principal: Principal, conversation_id: uuid.UUID | None, question: str
) -> ChatContext:
    """Create or load the user's conversation, save the question, load history.

    Raises ConversationNotFound before anything is written, so the HTTP layer
    can answer 404 before a stream starts.
    """
    tenant_id = principal.tenant_id
    async with tenant_transaction(tenant_id) as session:
        if conversation_id is None:
            conversation = await conversations_repo.create(
                session, tenant_id, principal.user_id
            )
        else:
            found = await conversations_repo.get_owned(
                session, tenant_id, principal.user_id, conversation_id
            )
            if found is None:
                raise ConversationNotFound
            conversation = found
        history_rows = await messages_repo.recent_history(
            session,
            tenant_id,
            principal.user_id,
            conversation.id,
            settings.chat_history_messages,
        )
        await messages_repo.add(
            session,
            tenant_id,
            principal.user_id,
            conversation.id,
            role="user",
            content=question,
            status="complete",
        )
        await conversations_repo.touch(
            session, tenant_id, principal.user_id, conversation.id
        )
        return ChatContext(
            principal=principal,
            conversation_id=conversation.id,
            question=question,
            history=[{"role": m.role, "content": m.content} for m in history_rows],
        )


@dataclass
class _Outcome:
    status: str = "interrupted"  # what a disconnect leaves behind
    parts: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    error_code: str | None = None


async def stream_answer(
    ctx: ChatContext, embedder: EmbeddingProvider, llm: LLMProvider
) -> AsyncIterator[ChatEvent]:
    outcome = _Outcome()
    try:
        async for event in _run(ctx, embedder, llm, outcome):
            yield event
    except LLMError as exc:
        logger.warning("chat llm failed: error=%s", type(exc).__name__)
        outcome.status, outcome.error_code = "failed", exc.code
    except Exception as exc:  # noqa: BLE001 - logged by class; never leaves the stream
        _log_failure("chat failed", exc, ctx)
        outcome.status, outcome.error_code = "failed", INTERNAL_ERROR
    finally:
        # Also runs for CancelledError / GeneratorExit (status stays
        # "interrupted"); the shield lets the save finish if the task is cancelled.
        saved = await asyncio.shield(_save_assistant(ctx, outcome))
    if outcome.error_code is not None:
        yield ErrorEvent(outcome.error_code)
    elif not saved:
        yield ErrorEvent(INTERNAL_ERROR)
    elif outcome.status == "no_answer":
        yield DoneEvent(status="no_answer", cited=[])
    else:
        text = "".join(outcome.parts)
        yield DoneEvent(
            status=outcome.status, cited=parse_citations(text, len(outcome.sources))
        )


async def chat_events(
    principal: Principal,
    conversation_id: uuid.UUID | None,
    question: str,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
) -> AsyncIterator[ChatEvent]:
    ctx = await prepare_chat(principal, conversation_id, question)
    async for event in stream_answer(ctx, embedder, llm):
        yield event


async def _run(
    ctx: ChatContext,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    outcome: _Outcome,
) -> AsyncIterator[ChatEvent]:
    tenant_id = ctx.principal.tenant_id
    embedding = await embedder.embed_query(ctx.question)  # no transaction open
    async with tenant_transaction(tenant_id) as session:
        result = await search_in_session(
            session, tenant_id, embedding, settings.chat_top_k
        )
        titles = await documents_repo.titles_for(
            session, tenant_id, list({hit.document_id for hit in result.hits})
        )
    qualified = [
        PromptSource(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            document_title=titles[hit.document_id],
            chunk_index=hit.chunk_index,
            content=hit.content,
            score=hit.score,
        )
        for hit in result.hits
        if hit.score >= settings.min_retrieval_score and hit.document_id in titles
    ]
    if not qualified:
        outcome.status = "no_answer"
        outcome.parts.append(REFUSAL_TEXT)
        yield SourcesEvent([])
        yield TokenEvent(REFUSAL_TEXT)
        return

    built = build_messages(ctx.history, qualified, ctx.question)
    infos = [
        SourceInfo(
            index=i,
            chunk_id=s.chunk_id,
            document_id=s.document_id,
            document_title=s.document_title,
            chunk_index=s.chunk_index,
            score=s.score,
        )
        for i, s in enumerate(built.sources, 1)
    ]
    outcome.sources = [
        {
            "index": i.index,
            "chunk_id": str(i.chunk_id),
            "document_id": str(i.document_id),
            "document_title": i.document_title,
            "chunk_index": i.chunk_index,
            "score": i.score,
        }
        for i in infos
    ]
    outcome.model = settings.groq_model
    yield SourcesEvent(infos)
    # No transaction is open while the model streams.
    async for token in llm.stream_chat(
        built.messages, max_tokens=settings.max_answer_tokens
    ):
        outcome.parts.append(token)
        yield TokenEvent(token)
    outcome.status = "complete"


async def _save_assistant(ctx: ChatContext, outcome: _Outcome) -> bool:
    tenant_id = ctx.principal.tenant_id
    try:
        async with tenant_transaction(tenant_id) as session:
            await messages_repo.add(
                session,
                tenant_id,
                ctx.principal.user_id,
                ctx.conversation_id,
                role="assistant",
                content="".join(outcome.parts),
                status=outcome.status,
                sources=outcome.sources,
                model=outcome.model,
            )
            await conversations_repo.touch(
                session, tenant_id, ctx.principal.user_id, ctx.conversation_id
            )
    except Exception as exc:  # noqa: BLE001 - logged by class; never leaves the stream
        _log_failure("chat save failed", exc, ctx)
        return False
    return True


def _log_failure(message: str, exc: BaseException, ctx: ChatContext) -> None:
    """Class name, SQLSTATE, ids and traceback frames only (no exception text)."""
    frames = " > ".join(
        f"{Path(f.filename).name}:{f.lineno} in {f.name}"
        for f in traceback.extract_tb(exc.__traceback__)
    )
    logger.error(
        "%s: tenant=%s conversation=%s error=%s sqlstate=%s frames=%s",
        message,
        ctx.principal.tenant_id,
        ctx.conversation_id,
        type(exc).__name__,
        sqlstate_of(exc),
        frames,
    )
