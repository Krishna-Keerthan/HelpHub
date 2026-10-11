"""Chat orchestration: event order, short transactions, failures, disconnects."""

import asyncio
import logging
import uuid

import groq
import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.services import chat
from app.services.chat import (
    ConversationNotFound,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    TokenEvent,
)
from app.services.llm import GroqProvider
from tests.chat_helpers import (
    AxisQueryEmbedder,
    BrokenEmbedder,
    checked_out_connections,
    message_rows,
    principal_of,
    seed_chunk,
)
from tests.conftest import MakeTenant, SeededTenant
from tests.fakes import FakeClient, FakeLLMProvider, FakeStream, chunk
from tests.ingestion_helpers import idle_in_transaction

TOKENS = ["t0 ", "t1 ", "t2 ", "t3 ", "t4 [1]"]
QUESTION = "how do I reset?"


@pytest.fixture(autouse=True)
def threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "min_retrieval_score", 0.6)


async def seeded(owner_conn: AsyncConnection, make_tenant: MakeTenant):
    tenant = await make_tenant()
    await seed_chunk(owner_conn, tenant)
    return tenant


async def start(tenant: SeededTenant, llm, embedder=None):
    ctx = await chat.prepare_chat(principal_of(tenant), None, QUESTION)
    return ctx, chat.stream_answer(ctx, embedder or AxisQueryEmbedder(), llm)


async def test_sources_come_first_then_tokens_then_done(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider(tokens=TOKENS)
    _, stream = await start(tenant, llm)
    events = [e async for e in stream]
    assert isinstance(events[0], SourcesEvent) and len(events[0].sources) == 1
    assert events[1:-1] == [TokenEvent(t) for t in TOKENS]
    assert events[-1] == DoneEvent(status="complete", cited=[1])
    _, assistant = await message_rows(owner_conn, tenant["id"])
    assert (assistant["status"], assistant["content"]) == ("complete", "".join(TOKENS))
    assert assistant["model"] == settings.groq_model
    assert len(assistant["sources"]) == 1


async def test_citations_are_validated_against_the_sources_shown(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider(tokens=["see [1] and [7] and [0]"])
    _, stream = await start(tenant, llm)
    events = [e async for e in stream]
    assert events[-1] == DoneEvent(status="complete", cited=[1])


async def test_no_transaction_or_connection_is_held_while_streaming(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider(tokens=TOKENS, delay=0.01)
    _, stream = await start(tenant, llm)
    checks = 0
    async for event in stream:
        if isinstance(event, TokenEvent):
            assert checked_out_connections() == 0
            assert await idle_in_transaction(owner_conn) == 0
            checks += 1
    assert checks == len(TOKENS)


async def test_assistant_message_is_saved_only_after_streaming_completes(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider(tokens=TOKENS)
    _, stream = await start(tenant, llm)
    async for event in stream:
        if isinstance(event, TokenEvent) and event.text == "t1 ":
            rows = await message_rows(owner_conn, tenant["id"])
            assert [r["role"] for r in rows] == ["user"]
    assert [r["role"] for r in await message_rows(owner_conn, tenant["id"])] == [
        "user",
        "assistant",
    ]


async def test_llm_failure_mid_stream_saves_failed_with_partial_text(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider(tokens=TOKENS, fail_at=2)
    _, stream = await start(tenant, llm)
    events = [e async for e in stream]
    assert events[1:3] == [TokenEvent("t0 "), TokenEvent("t1 ")]
    assert events[-1] == ErrorEvent("llm_unavailable")
    assert not any(isinstance(e, DoneEvent) for e in events)
    _, assistant = await message_rows(owner_conn, tenant["id"])
    assert (assistant["status"], assistant["content"]) == ("failed", "t0 t1 ")


async def test_unexpected_provider_error_text_never_reaches_stream_or_logs(
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    secret = "PROVIDER-SECRET-BODY"
    llm = FakeLLMProvider(tokens=TOKENS, fail_at=1, error=RuntimeError(secret))
    _, stream = await start(tenant, llm)
    with caplog.at_level(logging.DEBUG):
        events = [e async for e in stream]
    assert events[-1] == ErrorEvent("internal_error")
    assert secret not in repr(events)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text
    rows = await message_rows(owner_conn, tenant["id"])
    assert secret not in repr(rows)


async def test_embedding_failure_saves_failed_row_with_no_llm_call_and_no_leak(
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider()
    _, stream = await start(tenant, llm, BrokenEmbedder())
    with caplog.at_level(logging.DEBUG):
        events = [e async for e in stream]
    assert events == [ErrorEvent("internal_error")]
    assert llm.calls == 0
    assert "EMBED-SECRET-TEXT" not in repr(events) + caplog.text
    assert "RuntimeError" in caplog.text
    user_row, assistant = await message_rows(owner_conn, tenant["id"])
    assert user_row["status"] == "complete"
    assert (assistant["status"], assistant["content"]) == ("failed", "")
    assert "EMBED-SECRET-TEXT" not in repr(assistant)


async def test_empty_groq_key_gives_llm_unavailable_without_network(
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "groq_api_key", SecretStr(""))
    tenant = await seeded(owner_conn, make_tenant)

    class NoClient:
        def __getattr__(self, name: str):
            raise AssertionError("client must not be touched")

    _, stream = await start(tenant, GroqProvider(NoClient()))
    events = [e async for e in stream]
    assert isinstance(events[0], SourcesEvent)
    assert events[-1] == ErrorEvent("llm_unavailable")
    _, assistant = await message_rows(owner_conn, tenant["id"])
    assert (assistant["status"], assistant["content"]) == ("failed", "")


async def test_cancelling_the_consumer_saves_interrupted_partial_text(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider(tokens=TOKENS, delay=0.05)
    _, stream = await start(tenant, llm)
    received: list[str] = []

    async def consume() -> None:
        async for event in stream:
            if isinstance(event, TokenEvent):
                received.append(event.text)

    task = asyncio.create_task(consume())
    while len(received) < 2:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    _, assistant = await message_rows(owner_conn, tenant["id"])
    assert assistant["status"] == "interrupted"
    assert assistant["content"] == "".join(received) != ""
    assert len(received) < len(TOKENS)


async def test_aclose_after_n_tokens_saves_interrupted_partial_text(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider(tokens=TOKENS)
    _, stream = await start(tenant, llm)
    received: list[str] = []
    async for event in stream:
        if isinstance(event, TokenEvent):
            received.append(event.text)
            if len(received) == 2:
                break
    await stream.aclose()
    _, assistant = await message_rows(owner_conn, tenant["id"])
    assert assistant["status"] == "interrupted"
    assert assistant["content"] == "t0 t1 "


async def test_second_turn_sees_the_first_turn_as_history(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await seeded(owner_conn, make_tenant)
    llm = FakeLLMProvider(tokens=["first answer [1]"])
    ctx, stream = await start(tenant, llm)
    _ = [e async for e in stream]
    ctx2 = await chat.prepare_chat(principal_of(tenant), ctx.conversation_id, "again?")
    assert [(m["role"], m["content"]) for m in ctx2.history] == [
        ("user", QUESTION),
        ("assistant", "first answer [1]"),
    ]
    _ = [e async for e in chat.stream_answer(ctx2, AxisQueryEmbedder(), llm)]
    contents = [m["content"] for m in llm.last_messages]
    assert QUESTION in contents and "first answer [1]" in contents
    assert contents[-1] == "again?"


async def test_foreign_or_unknown_conversation_is_not_found_and_writes_nothing(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    ctx = await chat.prepare_chat(principal_of(a), None, "mine")
    with pytest.raises(ConversationNotFound):
        await chat.prepare_chat(principal_of(b), ctx.conversation_id, "steal")
    with pytest.raises(ConversationNotFound):
        await chat.prepare_chat(principal_of(a), uuid.uuid4(), "nope")
    assert await message_rows(owner_conn, b["id"]) == []
    assert len(await message_rows(owner_conn, a["id"])) == 1


async def test_reasoning_text_reaches_neither_client_events_nor_the_saved_row(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    thought = "PRIVATE-CHAIN-OF-THOUGHT"
    client = FakeClient(
        [
            FakeStream(
                [
                    chunk(None, reasoning=thought, channel="analysis"),
                    chunk("Reset it ", channel="final"),
                    chunk(None, reasoning=thought, channel="analysis"),
                    chunk("in Settings [1].", reasoning=thought, channel="final"),
                ]
            )
        ]
    )
    tenant = await seeded(owner_conn, make_tenant)
    _, stream = await start(tenant, GroqProvider(client))
    events = [e async for e in stream]
    assert thought not in repr(events)
    assert [e.text for e in events if isinstance(e, TokenEvent)] == [
        "Reset it ",
        "in Settings [1].",
    ]
    _, assistant = await message_rows(owner_conn, tenant["id"])
    assert assistant["status"] == "complete"
    assert assistant["content"] == "Reset it in Settings [1]."
    assert thought not in repr(assistant)


async def test_zero_content_stream_saves_a_failed_row_not_an_empty_answer(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    client = FakeClient([FakeStream([chunk(None, reasoning="only thinking")])])
    tenant = await seeded(owner_conn, make_tenant)
    _, stream = await start(tenant, GroqProvider(client))
    events = [e async for e in stream]
    assert events[-1] == ErrorEvent("llm_empty_response")
    assert not any(isinstance(e, DoneEvent) for e in events)
    _, assistant = await message_rows(owner_conn, tenant["id"])
    assert (assistant["status"], assistant["content"]) == ("failed", "")


async def test_retired_model_404_saves_a_failed_row_with_model_unavailable(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    response = httpx.Response(
        404, request=httpx.Request("POST", "https://example.invalid/chat")
    )
    client = FakeClient(
        [groq.NotFoundError("PROVIDER-TEXT", response=response, body=None)]
    )
    tenant = await seeded(owner_conn, make_tenant)
    _, stream = await start(tenant, GroqProvider(client))
    events = [e async for e in stream]
    assert events[-1] == ErrorEvent("llm_model_unavailable")
    assert "PROVIDER-TEXT" not in repr(events)
    _, assistant = await message_rows(owner_conn, tenant["id"])
    assert assistant["status"] == "failed"
