"""GroqProvider with an injected fake client: mapping, retries, no key, no leaks."""

import logging
import socket

import groq
import httpx
import pytest
from pydantic import SecretStr

from app.api.deps import get_llm_provider
from app.core.config import settings
from app.main import app, lifespan
from app.services import llm as llm_module
from app.services.llm import (
    GroqProvider,
    LLMBadRequestError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from tests.fakes import FakeClient, FakeStream, chunk

SECRET = "PROVIDER-SECRET-TEXT"
REQ = httpx.Request("POST", "https://example.invalid/chat")


def status_error(cls: type, code: int, headers: dict[str, str] | None = None):
    response = httpx.Response(code, headers=headers or {}, request=REQ)
    return cls(SECRET, response=response, body=None)


@pytest.fixture(autouse=True)
def key_and_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("test-key"))
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(llm_module, "_sleep", fake_sleep)
    return delays


async def collect(provider: GroqProvider) -> list[str]:
    return [
        t
        async for t in provider.stream_chat(
            [{"role": "user", "content": "q"}], max_tokens=50
        )
    ]


async def test_streams_tokens_and_passes_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "groq_model", "some/plain-model")
    client = FakeClient([FakeStream([chunk("a"), chunk(None), chunk("b")])])
    assert await collect(GroqProvider(client)) == ["a", "b"]
    call = client.calls[0]
    assert call["stream"] is True
    assert call["max_completion_tokens"] == 50
    assert call["model"] == settings.groq_model
    assert call["temperature"] == settings.llm_temperature
    assert "max_tokens" not in call
    # Reasoning parameters are for gpt-oss only; other models would reject them.
    for name in ("reasoning_effort", "include_reasoning", "reasoning_format"):
        assert name not in call


async def test_retries_before_first_token_then_succeeds(
    key_and_sleep: list[float],
) -> None:
    client = FakeClient(
        [status_error(groq.InternalServerError, 503), FakeStream([chunk("ok")])]
    )
    assert await collect(GroqProvider(client)) == ["ok"]
    assert len(client.calls) == 2
    assert len(key_and_sleep) == 1


async def test_retries_are_capped_at_two() -> None:
    client = FakeClient([status_error(groq.InternalServerError, 500) for _ in range(5)])
    with pytest.raises(LLMUnavailableError):
        await collect(GroqProvider(client))
    assert len(client.calls) == 3  # first try + 2 retries


async def test_retry_after_is_honoured_and_capped(key_and_sleep: list[float]) -> None:
    client = FakeClient(
        [
            status_error(groq.RateLimitError, 429, {"retry-after": "120"}),
            status_error(groq.RateLimitError, 429, {"retry-after": "2"}),
            FakeStream([chunk("ok")]),
        ]
    )
    assert await collect(GroqProvider(client)) == ["ok"]
    assert key_and_sleep == [5.0, 2.0]


async def test_retry_stops_at_overall_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_retry_deadline_seconds", 1.0)
    client = FakeClient([status_error(groq.RateLimitError, 429, {"retry-after": "5"})])
    with pytest.raises(LLMRateLimitError):
        await collect(GroqProvider(client))
    assert len(client.calls) == 1


async def test_no_retry_after_first_token() -> None:
    boom = status_error(groq.InternalServerError, 500)
    client = FakeClient([FakeStream([chunk("a"), boom]), FakeStream([chunk("zzz")])])
    seen: list[str] = []
    with pytest.raises(LLMUnavailableError):
        async for token in GroqProvider(client).stream_chat([], max_tokens=5):
            seen.append(token)
    assert seen == ["a"]
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (status_error(groq.BadRequestError, 400), LLMBadRequestError),
        (status_error(groq.AuthenticationError, 401), LLMUnavailableError),
        (groq.APITimeoutError(request=REQ), LLMTimeoutError),
        (groq.APIConnectionError(request=REQ), LLMUnavailableError),
    ],
)
async def test_errors_map_to_our_types_without_provider_text(
    raised: BaseException, expected: type[LLMError]
) -> None:
    client = FakeClient([raised] * 3)
    with pytest.raises(expected) as info:
        await collect(GroqProvider(client))
    assert SECRET not in str(info.value)
    assert SECRET not in repr(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__


async def test_empty_key_fails_without_touching_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "groq_api_key", SecretStr(""))
    client = FakeClient([])
    with pytest.raises(LLMUnavailableError):
        await collect(GroqProvider(client))
    assert client.calls == []


def test_real_dependency_resolves_to_groq_provider_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    override = app.dependency_overrides.pop(get_llm_provider, None)
    try:
        assert isinstance(get_llm_provider(), GroqProvider)
    finally:
        if override is not None:
            app.dependency_overrides[get_llm_provider] = override


GPT_OSS = "openai/gpt-oss-20b"


async def test_gpt_oss_gets_low_effort_hidden_reasoning_and_token_headroom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "groq_model", GPT_OSS)
    monkeypatch.setattr(settings, "llm_reasoning_effort", "low")
    monkeypatch.setattr(settings, "llm_reasoning_token_headroom", 512)
    client = FakeClient([FakeStream([chunk("a")])])
    await collect(GroqProvider(client))
    call = client.calls[0]
    assert call["model"] == GPT_OSS
    assert call["reasoning_effort"] == "low"
    assert call["include_reasoning"] is False
    # include_reasoning is mutually exclusive with reasoning_format (SDK docs).
    assert "reasoning_format" not in call
    # Reasoning tokens count against the completion budget, so the answer
    # budget (50) is topped up by the headroom.
    assert call["max_completion_tokens"] == 50 + 512


async def test_reasoning_effort_setting_is_what_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "groq_model", GPT_OSS)
    monkeypatch.setattr(settings, "llm_reasoning_effort", "medium")
    client = FakeClient([FakeStream([chunk("a")])])
    await collect(GroqProvider(client))
    assert client.calls[0]["reasoning_effort"] == "medium"


async def test_reasoning_deltas_are_never_yielded() -> None:
    thought = "PRIVATE-CHAIN-OF-THOUGHT"
    client = FakeClient(
        [
            FakeStream(
                [
                    chunk(None, reasoning=thought, channel="analysis"),
                    chunk("Hel", channel="final"),
                    chunk(None, reasoning=thought + " more", channel="analysis"),
                    chunk("lo", reasoning=thought, channel="final"),
                ]
            )
        ]
    )
    tokens = await collect(GroqProvider(client))
    assert tokens == ["Hel", "lo"]
    assert thought not in "".join(tokens)


@pytest.mark.parametrize(
    "items",
    [[], [chunk(None)], [chunk(None, reasoning="only thinking"), chunk("")]],
)
async def test_stream_with_no_content_is_an_error_not_an_empty_answer(
    items: list,
) -> None:
    stream = FakeStream(items)
    client = FakeClient([stream])
    with pytest.raises(LLMError) as info:
        await collect(GroqProvider(client))
    assert info.value.code == "llm_empty_response"
    assert stream.closed
    assert len(client.calls) == 1  # not retried


async def test_404_is_model_unavailable_and_logs_the_model_not_provider_text(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "groq_model", "retired/model-x")
    client = FakeClient([status_error(groq.NotFoundError, 404)])
    with caplog.at_level(logging.DEBUG), pytest.raises(LLMBadRequestError) as info:
        await collect(GroqProvider(client))
    assert info.value.code == "llm_model_unavailable"
    assert SECRET not in str(info.value) + repr(info.value)
    assert "retired/model-x" in caplog.text
    assert SECRET not in caplog.text
    assert len(client.calls) == 1  # a missing model is not retried


async def test_one_shared_client_is_reused_and_closed_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_module, "_client", None)
    monkeypatch.setattr(settings, "warm_up_embeddings", False)
    first = llm_module.get_groq_client()
    assert llm_module.get_groq_client() is first
    closed: list[bool] = []

    async def fake_close() -> None:
        closed.append(True)

    monkeypatch.setattr(first, "close", fake_close)
    async with lifespan(app):
        pass
    assert closed == [True]
    assert llm_module._client is None
