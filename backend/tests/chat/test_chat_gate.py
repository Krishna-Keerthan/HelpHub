"""The retrieval gate: below min_retrieval_score the LLM is never called."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import Principal
from app.core.config import settings
from app.db.tenant_context import tenant_transaction
from app.services import chat
from app.services.chat import (
    REFUSAL_TEXT,
    DoneEvent,
    SourcesEvent,
    TokenEvent,
)
from app.services.embeddings import FakeEmbeddingProvider
from app.services.search import search_in_session
from tests.conftest import (
    MakeTenant,
    SeededTenant,
    insert_chunk,
    insert_document,
    unit_vector,
)
from tests.helpers.fakes import FakeLLMProvider

THRESHOLD = 0.6
QUESTION = "uniq-question-4711 how do I reset?"


class AxisQueryEmbedder(FakeEmbeddingProvider):
    """Every query embeds to the first axis, so chunk scores are chosen."""

    async def embed_query(self, text: str) -> list[float]:
        return unit_vector(1.0)


def with_score(score: float) -> list[float]:
    return unit_vector(score, (1 - score**2) ** 0.5)


@pytest.fixture(autouse=True)
def threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "min_retrieval_score", THRESHOLD)


def principal_of(tenant: SeededTenant) -> Principal:
    return Principal(user_id=tenant["user_id"], tenant_id=tenant["id"], role="admin")


async def seed_chunk(
    owner_conn: AsyncConnection,
    tenant: SeededTenant,
    score: float,
    content: str,
    index: int = 0,
) -> uuid.UUID:
    document_id = await insert_document(
        owner_conn, tenant["id"], created_by=tenant["user_id"], title=f"Doc {content}"
    )
    chunk_id = await insert_chunk(
        owner_conn,
        tenant["id"],
        document_id,
        chunk_index=index,
        content=content,
        embedding=with_score(score),
    )
    await owner_conn.commit()
    return chunk_id


async def ask(tenant: SeededTenant, llm: FakeLLMProvider) -> list[Any]:
    ctx = await chat.prepare_chat(principal_of(tenant), None, QUESTION)
    return [event async for event in chat.stream_answer(ctx, AxisQueryEmbedder(), llm)]


async def rows(owner_conn: AsyncConnection, tenant: SeededTenant) -> list[Any]:
    result = await owner_conn.execute(
        text(
            "SELECT role, content, status, sources, model FROM chat_messages "
            "WHERE tenant_id = :t ORDER BY seq"
        ),
        {"t": tenant["id"]},
    )
    found = list(result.mappings())
    await owner_conn.rollback()
    return found


async def assert_refused(
    owner_conn: AsyncConnection, tenant: SeededTenant, llm: FakeLLMProvider, events
) -> None:
    assert llm.calls == 0
    assert events == [
        SourcesEvent([]),
        TokenEvent(REFUSAL_TEXT),
        DoneEvent(status="no_answer", cited=[]),
    ]
    user_row, assistant_row = await rows(owner_conn, tenant)
    assert (user_row["role"], user_row["content"], user_row["status"]) == (
        "user",
        QUESTION,
        "complete",
    )
    assert assistant_row["role"] == "assistant"
    assert assistant_row["status"] == "no_answer"
    assert assistant_row["content"] == REFUSAL_TEXT
    assert assistant_row["sources"] == []


async def test_below_threshold_refuses_without_calling_the_llm(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    await seed_chunk(owner_conn, tenant, THRESHOLD - 0.2, "weak match")
    llm = FakeLLMProvider()
    events = await ask(tenant, llm)
    await assert_refused(owner_conn, tenant, llm, events)


async def test_empty_tenant_gets_the_same_refusal(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    llm = FakeLLMProvider()
    events = await ask(tenant, llm)
    await assert_refused(owner_conn, tenant, llm, events)


async def measured_score(tenant: SeededTenant) -> float:
    async with tenant_transaction(tenant["id"]) as session:
        result = await search_in_session(session, tenant["id"], "", unit_vector(1.0), 1)
    return result.hits[0].score


async def test_score_exactly_at_threshold_calls_the_llm_once(
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await make_tenant()
    await seed_chunk(owner_conn, tenant, 0.8, "boundary chunk")
    monkeypatch.setattr(settings, "min_retrieval_score", await measured_score(tenant))
    llm = FakeLLMProvider()
    events = await ask(tenant, llm)
    assert llm.calls == 1
    assert isinstance(events[0], SourcesEvent) and len(events[0].sources) == 1
    assert events[-1].status == "complete"


async def test_threshold_just_above_the_score_does_not_call_the_llm(
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = await make_tenant()
    await seed_chunk(owner_conn, tenant, 0.8, "boundary chunk")
    monkeypatch.setattr(
        settings, "min_retrieval_score", await measured_score(tenant) + 1e-6
    )
    llm = FakeLLMProvider()
    events = await ask(tenant, llm)
    await assert_refused(owner_conn, tenant, llm, events)


async def test_hit_below_threshold_is_excluded_from_prompt_and_sources(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    strong = await seed_chunk(owner_conn, tenant, 0.9, "STRONG-CHUNK-TEXT", 0)
    await seed_chunk(owner_conn, tenant, 0.3, "WEAK-CHUNK-TEXT", 1)
    llm = FakeLLMProvider()
    events = await ask(tenant, llm)
    assert llm.calls == 1
    sources_event = events[0]
    assert isinstance(sources_event, SourcesEvent)
    assert [s.chunk_id for s in sources_event.sources] == [strong]
    prompt = "\n".join(m["content"] for m in llm.last_messages)
    assert "STRONG-CHUNK-TEXT" in prompt
    assert "WEAK-CHUNK-TEXT" not in prompt
    _, assistant_row = await rows(owner_conn, tenant)
    assert [s["chunk_id"] for s in assistant_row["sources"]] == [str(strong)]


def test_refusal_text_is_a_constant_without_user_input() -> None:
    assert isinstance(REFUSAL_TEXT, str) and REFUSAL_TEXT
    assert "uniq-question-4711" not in REFUSAL_TEXT
    assert chat.REFUSAL_TEXT is REFUSAL_TEXT


async def test_refusal_token_is_never_model_output(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    llm = FakeLLMProvider(tokens=["MODEL-SAID-THIS"])
    events = await ask(tenant, llm)
    assert "MODEL-SAID-THIS" not in str(events)
    assert llm.calls == 0


async def seed_keyword_only_chunk(
    owner_conn: AsyncConnection, tenant: SeededTenant, filler_score: float
) -> uuid.UUID:
    """50 vector-closer fillers push a low-cosine chunk out of the vector branch.

    The chunk is found only through the text branch (it holds the question's
    identifier-like token), with cosine 0.2 to the query.
    """
    document_id = await insert_document(
        owner_conn, tenant["id"], created_by=tenant["user_id"], title="Gate doc"
    )
    for i in range(50):
        await insert_chunk(
            owner_conn,
            tenant["id"],
            document_id,
            chunk_index=i,
            content=f"filler {i}",
            embedding=with_score(filler_score),
        )
    target = await insert_chunk(
        owner_conn,
        tenant["id"],
        document_id,
        chunk_index=50,
        content="KEYWORD-ONLY-TEXT uniq-question-4711",
        embedding=with_score(0.2),
    )
    await owner_conn.commit()
    async with tenant_transaction(tenant["id"]) as session:
        found = await search_in_session(
            session, tenant["id"], QUESTION, unit_vector(1.0), 5
        )
    by_id = {hit.chunk_id: hit for hit in found.hits}
    assert by_id[target].found_by == ("keyword",)  # precondition of both tests
    assert by_id[target].score < THRESHOLD
    return target


async def test_chunk_found_only_by_text_search_below_threshold_is_refused(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    """The gate looks at cosine, not at which branch found the chunk."""
    tenant = await make_tenant()
    await seed_keyword_only_chunk(owner_conn, tenant, filler_score=0.5)
    llm = FakeLLMProvider()
    events = await ask(tenant, llm)
    await assert_refused(owner_conn, tenant, llm, events)


async def test_text_only_chunk_below_threshold_is_left_out_of_the_prompt(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    target = await seed_keyword_only_chunk(owner_conn, tenant, filler_score=0.9)
    llm = FakeLLMProvider()
    events = await ask(tenant, llm)
    assert llm.calls == 1
    sources_event = events[0]
    assert isinstance(sources_event, SourcesEvent)
    assert target not in [s.chunk_id for s in sources_event.sources]
    assert "KEYWORD-ONLY-TEXT" not in "\n".join(m["content"] for m in llm.last_messages)
