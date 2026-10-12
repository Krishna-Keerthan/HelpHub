"""Test doubles for the LLM provider."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from types import SimpleNamespace
from typing import Any

from app.services.llm import LLMUnavailableError

DEFAULT_TOKENS = ("Reset ", "it ", "in ", "Settings ", "[1].")


class FakeLLMProvider:
    """Scripted token stream with an optional delay, failure and spy hook.

    ``fail_at=N`` raises ``error`` instead of yielding token N (0-based).
    ``calls`` counts stream_chat invocations; ``last_messages`` is the prompt.
    """

    def __init__(
        self,
        tokens: Sequence[str] = DEFAULT_TOKENS,
        *,
        delay: float = 0.0,
        fail_at: int | None = None,
        error: BaseException | None = None,
        on_call: Callable[[list[dict[str, str]]], None] | None = None,
        on_token: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        self.tokens = list(tokens)
        self.delay = delay
        self.fail_at = fail_at
        self.error = error or LLMUnavailableError()
        self.on_call = on_call
        self.on_token = on_token
        self.calls = 0
        self.last_messages: list[dict[str, str]] = []
        self.last_max_tokens: int | None = None
        self.yielded: list[str] = []

    async def stream_chat(
        self, messages: list[dict[str, str]], *, max_tokens: int
    ) -> AsyncIterator[str]:
        self.calls += 1
        self.last_messages = messages
        self.last_max_tokens = max_tokens
        if self.on_call is not None:
            self.on_call(messages)
        for i, token in enumerate(self.tokens):
            if self.fail_at == i:
                raise self.error
            if self.on_token is not None:
                await self.on_token(i)
            if self.delay:
                await asyncio.sleep(self.delay)
            self.yielded.append(token)
            yield token
        if self.fail_at is not None and self.fail_at >= len(self.tokens):
            raise self.error


def chunk(
    content: str | None, *, reasoning: str | None = None, channel: str | None = None
) -> Any:
    """A Groq-shaped streaming chunk. gpt-oss deltas also carry ``reasoning``
    (and an undeclared ``channel``) unless include_reasoning=False was sent."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content, reasoning=reasoning, channel=channel
                )
            )
        ]
    )


class FakeStream:
    """Stands in for the groq stream object; exceptions in ``items`` are raised."""

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
