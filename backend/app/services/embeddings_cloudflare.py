"""Cloudflare Workers AI embeddings (bge-small-en-v1.5), the production provider.

Every failure is mapped to ``EmbeddingUnavailableError`` with a fixed message:
provider text (which can echo inputs, account ids or request ids) never leaves
this module. Retries: at most ``MAX_RETRIES``, only on HTTP 429 and 5xx.
"""

import asyncio
import json
import logging
import math
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.embeddings import (
    EMBEDDING_DIM,
    EmbeddingUnavailableError,
    validate_vectors,
)

logger = logging.getLogger(__name__)
# httpx logs every request line at INFO, URL included, and the URL carries the
# account id. Warnings and errors stay visible.
logging.getLogger("httpx").setLevel(logging.WARNING)

CLOUDFLARE_MODEL_NAME = "@cf/baai/bge-small-en-v1.5"
# Sent on every request. The model's default is mean pooling; the local
# bge-small-en-v1.5 (and the vectors already stored) use CLS pooling.
POOLING = "cls"
# Our own cap per request, not a documented limit. A spike saw 5,000 inputs
# accepted and 10,000 rejected with HTTP 500 {"code":3043}; 100 keeps one call
# short and its failure cheap to retry.
CLOUDFLARE_BATCH_SIZE = 100
MAX_RETRIES = 2
BASE_BACKOFF_SECONDS = 0.5
MAX_RETRY_AFTER_SECONDS = 5.0
_API = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"

# Patched in tests.
_sleep = asyncio.sleep

_client: httpx.AsyncClient | None = None
# Neurons billed to this process per the cf-ai-neurons response header
# (a number only; no content). Logged per call and summed here.
neurons_total = 0.0


def enable_metrics_logging() -> None:
    """Make this module's INFO lines (one per call, with ``neurons=``) visible.

    The app configures no root logger, so INFO is otherwise dropped under
    uvicorn. Only this logger is opened up; idempotent.
    """
    if not any(getattr(h, "_helphub_metrics", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(levelname)s:     %(name)s: %(message)s")
        )
        handler._helphub_metrics = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def get_client() -> httpx.AsyncClient:
    """One shared client per process, created on first use."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=settings.embedding_timeout_seconds,
            headers={
                "Authorization": "Bearer "
                + settings.cloudflare_api_token.get_secret_value()
            },
        )
    return _client


async def close_client() -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        await client.aclose()


def _retryable(response: httpx.Response) -> bool:
    return response.status_code == 429 or response.status_code >= 500


def _backoff(attempt: int, response: httpx.Response | None) -> float:
    if response is not None:
        try:
            return min(float(response.headers["retry-after"]), MAX_RETRY_AFTER_SECONDS)
        except (KeyError, ValueError):
            pass
    return BASE_BACKOFF_SECONDS * 2**attempt * (0.5 + random.random() / 2)  # noqa: S311 (jitter, not security)


def _record_neurons(response: httpx.Response, count: int) -> None:
    global neurons_total
    raw = response.headers.get("cf-ai-neurons")
    try:
        neurons = float(raw) if raw is not None else None
    except ValueError:
        neurons = None
    if neurons is not None:
        neurons_total += neurons
    logger.info(
        "embedding call: texts=%d neurons=%s",
        count,
        raw if neurons is not None else "-",
    )


class CloudflareEmbeddingProvider:
    """bge-small-en-v1.5 on Workers AI over one shared httpx client."""

    dim = EMBEDDING_DIM
    model_name = CLOUDFLARE_MODEL_NAME

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def _post(self, texts: Sequence[str]) -> list[list[float]]:
        url = _API.format(
            account=settings.cloudflare_account_id.get_secret_value(),
            model=self.model_name,
        )
        body = {"text": list(texts), "pooling": POOLING}
        client = self._client or get_client()
        response: httpx.Response | None = None
        for attempt in range(MAX_RETRIES + 1):
            response = None
            try:
                response = await client.post(url, json=body)
            except httpx.HTTPError as exc:
                logger.warning("embedding call failed: error=%s", type(exc).__name__)
                retry = True
            else:
                retry = _retryable(response)
                if response.status_code == 200:
                    return self._parse(response, len(texts))
                logger.warning("embedding call failed: status=%d", response.status_code)
            if not retry or attempt == MAX_RETRIES:
                break
            await _sleep(_backoff(attempt, response))
        raise EmbeddingUnavailableError()

    def _parse(self, response: httpx.Response, count: int) -> list[list[float]]:
        try:
            payload: Any = response.json()
            data = payload["result"]["data"]
            vectors = validate_vectors(data, count=count, dim=self.dim)
        except Exception as exc:  # noqa: BLE001 - mapped to the generic error below
            logger.warning("embedding response unusable: error=%s", type(exc).__name__)
            raise EmbeddingUnavailableError() from None
        _record_neurons(response, count)
        return vectors

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), CLOUDFLARE_BATCH_SIZE):
            vectors.extend(await self._post(texts[i : i + CLOUDFLARE_BATCH_SIZE]))
        return validate_vectors(vectors, count=len(texts), dim=self.dim)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._post([text]))[0]


REFERENCE_FILE = Path(__file__).with_name("embedding_reference.json")
REFERENCE_MIN_COSINE = 0.999
# Startup must not wait on Cloudflare for long: the check is only a warning.
REFERENCE_CHECK_TIMEOUT_SECONDS = 8.0


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


async def reference_cosine(provider: CloudflareEmbeddingProvider) -> float:
    """Cosine between the hosted vector of the fixed sentence and the stored local one."""
    reference = json.loads(REFERENCE_FILE.read_text())
    hosted = (await provider.embed_passages([reference["sentence"]]))[0]
    return _cosine(hosted, reference["vector"])


async def warn_if_reference_differs(provider: CloudflareEmbeddingProvider) -> None:
    """Startup check, log-only: a mismatch or an outage never blocks readiness."""
    try:
        cosine = await asyncio.wait_for(
            reference_cosine(provider), REFERENCE_CHECK_TIMEOUT_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 - startup check must never raise
        logger.warning(
            "embedding reference check skipped: error=%s", type(exc).__name__
        )
        return
    if cosine < REFERENCE_MIN_COSINE:
        logger.warning(
            "embedding reference check FAILED: cosine=%.6f min=%s; hosted vectors "
            "may not match the stored ones (pooling or model changed?)",
            cosine,
            REFERENCE_MIN_COSINE,
        )
    else:
        logger.info("embedding reference check ok: cosine=%.6f", cosine)
