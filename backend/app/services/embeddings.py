"""Embedding providers: the real fastembed model and a deterministic fake.

Services depend on the ``EmbeddingProvider`` protocol. The API injects a
provider through ``app.api.deps.get_embedding_provider``; tests override it
with ``FakeEmbeddingProvider`` so they never load the model.
"""

import asyncio
import hashlib
import logging
import math
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384
FASTEMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
# backend/.cache is gitignored; fastembed would otherwise use a temp dir.
MODEL_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "fastembed"
# Max texts embedded per worker-thread call, so a big document never pins a
# thread (or memory) for one long uninterruptible call.
EMBED_BATCH_SIZE = 64


class EmbeddingError(Exception):
    """The provider returned vectors that do not match the request."""


def validate_vectors(
    vectors: Sequence[Sequence[float]], *, count: int, dim: int
) -> list[list[float]]:
    """Check count, per-vector length and finiteness; return plain float lists."""
    if len(vectors) != count:
        raise EmbeddingError(f"expected {count} vectors, got {len(vectors)}")
    for i, vec in enumerate(vectors):
        if len(vec) != dim:
            raise EmbeddingError(f"vector {i} has length {len(vec)}, expected {dim}")
        if not all(math.isfinite(x) for x in vec):
            raise EmbeddingError(f"vector {i} contains NaN or infinity")
    return [list(vec) for vec in vectors]


class EmbeddingProvider(Protocol):
    dim: int
    model_name: str

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class FastEmbedProvider:
    """bge-small-en-v1.5 via fastembed; inference runs in a worker thread."""

    dim = EMBEDDING_DIM
    model_name = FASTEMBED_MODEL_NAME

    # One shared model per process, loaded on first use.
    _model: Any = None
    _lock = threading.Lock()

    @classmethod
    def _get_model(cls) -> Any:
        with cls._lock:
            if cls._model is None:
                from fastembed import TextEmbedding

                cls._model = TextEmbedding(
                    model_name=cls.model_name, cache_dir=str(MODEL_CACHE_DIR)
                )
            return cls._model

    @classmethod
    def _passages(cls, texts: Sequence[str]) -> list[list[float]]:
        model = cls._get_model()
        # Materialize the lazy generator here, inside the worker thread.
        return [[float(x) for x in vec] for vec in model.passage_embed(list(texts))]

    @classmethod
    def _query(cls, text: str) -> list[float]:
        model = cls._get_model()
        return [float(x) for x in next(iter(model.query_embed(text)))]

    async def warm_up(self) -> None:
        await asyncio.to_thread(self._get_model)

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            vectors.extend(await asyncio.to_thread(self._passages, batch))
        return validate_vectors(vectors, count=len(texts), dim=self.dim)

    async def embed_query(self, text: str) -> list[float]:
        vector = await asyncio.to_thread(self._query, text)
        return validate_vectors([vector], count=1, dim=self.dim)[0]


class FakeEmbeddingProvider:
    """Deterministic, normalised, hash-seeded vectors for tests."""

    dim = EMBEDDING_DIM
    model_name = "fake-test-embeddings"

    def _vector(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        vec = np.random.default_rng(seed).standard_normal(self.dim)
        return (vec / np.linalg.norm(vec)).tolist()

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


_provider: FastEmbedProvider | None = None


def default_provider() -> FastEmbedProvider:
    """The process-wide real provider. Creating it does not load the model."""
    global _provider
    if _provider is None:
        _provider = FastEmbedProvider()
    return _provider


async def warm_up_default_provider() -> None:
    """Load the model at startup; on failure it will load lazily on first use."""
    try:
        await default_provider().warm_up()
    except Exception:
        logger.exception("embedding model warm-up failed; will retry on first use")


# --- Synchronous helpers -------------------------------------------------
# For tests and scripts ONLY. They block on model inference: never call them
# from async code (use an EmbeddingProvider there).


def get_embedding(text: str) -> list[float]:
    return FastEmbedProvider._passages([text])[0]


def get_embeddings_batch(texts: Sequence[str]) -> list[list[float]]:
    return FastEmbedProvider._passages(texts) if texts else []
