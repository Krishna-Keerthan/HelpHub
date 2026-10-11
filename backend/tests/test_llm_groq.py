"""GroqProvider with an injected fake client: mapping, retries, no key, no leaks."""

import socket
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import groq
import httpx
import pytest
from pydantic import SecretStr

from app.api.deps import get_llm_provider
from app.core.config import settings
from app.main import app
from app.services import llm as llm_module
from app.services.llm import (
    GroqProvider,
    LLMBadRequestError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from tests.fakes import chunk

SECRET = "PROVIDER-SECRET-TEXT"
REQ = httpx.Request("POST", "https://example.invalid/chat")


def status_error(cls: type, code: int, headers: dict[str, str] | None = None):
    response = httpx.Response(code, headers=headers or {}, request=REQ)
    return cls(SECRET, response=response, body=None)


class FakeStream:
    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.closed = False

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[Any]:
        for item in self.items:
            if isinstance(item, BaseException):
                raise item
            yield item

    async def close(self) -> None:
        self.closed = True


class FakeClient:
    """Each create() call pops the next scripted outcome (exception or stream)."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


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


async def test_streams_tokens_and_passes_parameters() -> None:
    client = FakeClient([FakeStream([chunk("a"), chunk(None), chunk("b")])])
    assert await collect(GroqProvider(client)) == ["a", "b"]
    call = client.calls[0]
    assert call["stream"] is True
    assert call["max_completion_tokens"] == 50
    assert call["model"] == settings.groq_model
    assert call["temperature"] == settings.llm_temperature
    assert "max_tokens" not in call


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
