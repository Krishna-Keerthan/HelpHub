"""Test doubles for the LLM provider."""

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
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
    ) -> None:
        self.tokens = list(tokens)
        self.delay = delay
        self.fail_at = fail_at
        self.error = error or LLMUnavailableError()
        self.on_call = on_call
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
            if self.delay:
                await asyncio.sleep(self.delay)
            self.yielded.append(token)
            yield token
        if self.fail_at is not None and self.fail_at >= len(self.tokens):
            raise self.error


def chunk(content: str | None) -> Any:
    """A Groq-shaped streaming chunk."""
    from types import SimpleNamespace

    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
    )
