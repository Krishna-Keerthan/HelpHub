"""Manual smoke test against the real Groq API. NOT part of pytest.

Run from backend/:  uv run python scripts/smoke_groq.py
Reads GROQ_API_KEY through app settings; never prints the key or the reply.

1. Lists the models Groq currently serves (GET /models) and fails clearly if
   the configured GROQ_MODEL is not among them.
2. Streams a fixed prompt with exactly the parameters GroqProvider sends and
   reports timing, token counts and the set of delta field names the model
   streamed (to learn what it emits, e.g. ``reasoning``).
"""

import asyncio
import sys
import time
from typing import Any

import groq

from app.core.config import settings
from app.services.llm import close_groq_client, get_groq_client, request_params

PROMPT = [{"role": "user", "content": "Reply with a short greeting."}]
# Smoke budget for the answer; request_params adds the reasoning headroom.
ANSWER_TOKENS = 50


async def active_model_ids(client: Any) -> set[str]:
    page = await client.models.list()
    ids: set[str] = set()
    for model in page.data:
        extra = model.model_extra or {}
        if extra.get("active", True):  # absent flag means listed = active
            ids.add(model.id)
    return ids


async def stream_once(client: Any) -> dict[str, Any]:
    params = request_params(PROMPT, ANSWER_TOKENS)
    started = time.monotonic()
    first_content: float | None = None
    content_chunks = 0
    delta_fields: set[str] = set()
    usage: Any = None
    stream = await client.chat.completions.create(**params)
    try:
        async for chunk in stream:
            if chunk.x_groq is not None and chunk.x_groq.usage is not None:
                usage = chunk.x_groq.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            delta_fields |= set(delta.model_dump(exclude_none=True))
            if delta.content:
                content_chunks += 1
                if first_content is None:
                    first_content = time.monotonic() - started
    finally:
        await stream.close()
    return {
        "params": {k: v for k, v in params.items() if k != "messages"},
        "first_content": first_content,
        "total": time.monotonic() - started,
        "content_chunks": content_chunks,
        "delta_fields": delta_fields,
        "usage": usage,
    }


async def main() -> int:
    if not settings.groq_api_key.get_secret_value():
        print("GROQ_API_KEY is not set")
        return 1
    client = get_groq_client()
    try:
        ids = await active_model_ids(client)
        print(f"active models ({len(ids)}): {', '.join(sorted(ids))}")
        if settings.groq_model not in ids:
            print(
                f"FAIL: configured GROQ_MODEL {settings.groq_model!r} is not served "
                "by Groq; pick one from the list above."
            )
            return 1
        result = await stream_once(client)
    except groq.GroqError as exc:
        print(f"FAIL: {type(exc).__name__} status={getattr(exc, 'status_code', None)}")
        return 1
    finally:
        await close_groq_client()
    usage = result["usage"]
    first = result["first_content"]
    print(f"model={settings.groq_model}")
    print(f"params={result['params']}")
    print(
        "time_to_first_content_token="
        + (f"{first:.2f}s" if first is not None else "n/a (no content!)")
    )
    print(f"total_time={result['total']:.2f}s")
    print(f"content_chunks={result['content_chunks']}")
    if usage is not None:
        details = usage.completion_tokens_details
        print(
            f"prompt_tokens={usage.prompt_tokens} "
            f"completion_tokens={usage.completion_tokens} "
            f"reasoning_tokens={details.reasoning_tokens if details else 'n/a'}"
        )
    print(f"delta_fields={sorted(result['delta_fields'])}")
    return 0 if first is not None else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
