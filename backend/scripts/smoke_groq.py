"""Manual smoke test against the real Groq API. NOT part of pytest.

Run from backend/:  uv run python scripts/smoke_groq.py
Reads GROQ_API_KEY through app settings; never prints the key or the reply.
"""

import asyncio
import sys
import time

from app.core.config import settings
from app.services.llm import GroqProvider, LLMError, close_groq_client

PROMPT = [{"role": "user", "content": "Reply with a short greeting."}]


async def main() -> int:
    if not settings.groq_api_key.get_secret_value():
        print("GROQ_API_KEY is not set")
        return 1
    started = time.monotonic()
    first_token_at: float | None = None
    tokens = 0
    try:
        async for _ in GroqProvider().stream_chat(PROMPT, max_tokens=50):
            if first_token_at is None:
                first_token_at = time.monotonic() - started
            tokens += 1
    except LLMError as exc:
        print(f"failed: {type(exc).__name__} ({exc.code})")
        return 1
    finally:
        await close_groq_client()
    total = time.monotonic() - started
    first = f"{first_token_at:.2f}s" if first_token_at is not None else "n/a"
    print(
        f"model={settings.groq_model} tokens={tokens} first_token={first} total={total:.2f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
