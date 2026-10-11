"""LLM provider protocol and the Groq implementation.

Errors are mapped to our own LLMError types with fixed messages: provider
text (which can echo prompts, keys or request ids) never leaves this module.
Retries happen only before the first token; once a token has been yielded a
failure is final, because the caller has already streamed partial output.
"""

import asyncio
import logging
import random
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

import groq
from groq import AsyncGroq

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
MAX_RETRY_AFTER_SECONDS = 5.0
BASE_BACKOFF_SECONDS = 0.5

Message = dict[str, str]

# Patched in tests.
_sleep = asyncio.sleep


class LLMError(Exception):
    """Base class. ``code`` is the generic client-facing error code."""

    code = "llm_error"
    message = "LLM request failed"

    def __init__(self) -> None:
        super().__init__(self.message)


class LLMUnavailableError(LLMError):
    code = "llm_unavailable"
    message = "LLM provider unavailable"


class LLMTimeoutError(LLMError):
    code = "llm_timeout"
    message = "LLM provider timed out"


class LLMRateLimitError(LLMError):
    code = "llm_rate_limited"
    message = "LLM provider rate limited"


class LLMBadRequestError(LLMError):
    code = "llm_bad_request"
    message = "LLM provider rejected the request"


class LLMProvider(Protocol):
    def stream_chat(
        self, messages: list[Message], *, max_tokens: int
    ) -> AsyncIterator[str]: ...


_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    """One shared client per process, created on first use."""
    global _client
    if _client is None:
        _client = AsyncGroq(
            api_key=settings.groq_api_key.get_secret_value(),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # we retry ourselves, and only before the first token
        )
    return _client


async def close_groq_client() -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        await client.close()


def _classify(exc: Exception) -> tuple[LLMError, bool]:
    """(our error, retryable) for a groq exception."""
    if isinstance(exc, groq.APITimeoutError):
        return LLMTimeoutError(), True
    if isinstance(exc, groq.APIConnectionError):
        return LLMUnavailableError(), True
    if isinstance(exc, groq.RateLimitError):
        return LLMRateLimitError(), True
    if isinstance(exc, groq.InternalServerError):
        return LLMUnavailableError(), True
    if isinstance(exc, groq.BadRequestError | groq.UnprocessableEntityError):
        return LLMBadRequestError(), False
    return LLMUnavailableError(), False  # auth, permission, anything else


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    raw = response.headers.get("retry-after") if response is not None else None
    try:
        return min(max(float(raw), 0.0), MAX_RETRY_AFTER_SECONDS)
    except (TypeError, ValueError):
        return None


def _backoff(attempt: int) -> float:
    return BASE_BACKOFF_SECONDS * 2**attempt * random.uniform(0.5, 1.0)


class GroqProvider:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    async def _open(
        self, messages: list[Message], max_tokens: int
    ) -> tuple[Any, Any, str | None]:
        """Open the stream and read its first token, retrying on failure.

        Returns (stream, iterator, first token); one iterator serves both reads.
        """
        client = self._client or get_groq_client()
        deadline = time.monotonic() + settings.llm_retry_deadline_seconds
        attempt = 0
        while True:
            stream: Any = None
            try:
                stream = await client.chat.completions.create(
                    model=settings.groq_model,
                    messages=messages,
                    max_completion_tokens=max_tokens,
                    temperature=settings.llm_temperature,
                    stream=True,
                )
                iterator = stream.__aiter__()
                return stream, iterator, await _first_token(iterator)
            except groq.GroqError as exc:
                if stream is not None:
                    await _close(stream)
                error, retryable = _classify(exc)
                logger.warning(
                    "llm open failed: %s attempt=%d", type(exc).__name__, attempt
                )
                delay = _retry_after(exc)
                if delay is None:
                    delay = _backoff(attempt)
                if (
                    not retryable
                    or attempt >= MAX_RETRIES
                    or time.monotonic() + delay > deadline
                ):
                    raise error from None
                attempt += 1
                await _sleep(delay)

    async def stream_chat(
        self, messages: list[Message], *, max_tokens: int
    ) -> AsyncIterator[str]:
        if not settings.groq_api_key.get_secret_value():
            raise LLMUnavailableError()
        stream, iterator, first = await self._open(messages, max_tokens)
        try:
            if first is None:
                return
            yield first
            try:
                async for item in iterator:
                    token = _delta(item)
                    if token:
                        yield token
            except groq.GroqError as exc:
                logger.warning("llm stream failed: %s", type(exc).__name__)
                raise _classify(exc)[0] from None
        finally:
            await _close(stream)


def _delta(item: Any) -> str | None:
    if not item.choices:
        return None
    return item.choices[0].delta.content


async def _first_token(iterator: Any) -> str | None:
    async for item in iterator:
        token = _delta(item)
        if token:
            return token
    return None


async def _close(stream: Any) -> None:
    try:
        await stream.close()
    except (OSError, groq.GroqError):  # best effort; never mask the outcome
        logger.debug("llm stream close failed")
