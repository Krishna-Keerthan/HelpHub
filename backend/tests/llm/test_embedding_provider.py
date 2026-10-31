import numpy as np
import pytest

from app.services.embeddings import (
    EmbeddingError,
    FakeEmbeddingProvider,
    FastEmbedProvider,
)


class StubModel:
    """Stands in for fastembed's TextEmbedding; returns lazy generators."""

    def __init__(self, dim: int = 384, drop: int = 0, bad_value: float | None = None):
        self.dim = dim
        self.drop = drop
        self.bad_value = bad_value
        self.batch_sizes: list[int] = []

    def passage_embed(self, texts):
        self.batch_sizes.append(len(texts))
        for _ in range(len(texts) - self.drop):
            vec = np.ones(self.dim, dtype=np.float32)
            if self.bad_value is not None:
                vec[0] = self.bad_value
            yield vec

    def query_embed(self, text):
        yield from self.passage_embed([text])


@pytest.mark.asyncio
async def test_fake_provider_is_deterministic_normalised_and_384d():
    fake = FakeEmbeddingProvider()
    a1, a2, b = await fake.embed_passages(["alpha", "alpha", "beta"])
    assert a1 == a2
    assert a1 != b
    assert len(a1) == fake.dim == 384
    assert np.linalg.norm(a1) == pytest.approx(1.0, rel=1e-6)
    assert await fake.embed_query("alpha") == a1
    assert await fake.embed_passages([]) == []


async def test_wrong_dimension_raises_embedding_error(monkeypatch):
    monkeypatch.setattr(FastEmbedProvider, "_model", StubModel(dim=3))
    with pytest.raises(EmbeddingError, match="length 3, expected 384"):
        await FastEmbedProvider().embed_passages(["a"])
    with pytest.raises(EmbeddingError, match="length 3, expected 384"):
        await FastEmbedProvider().embed_query("a")


async def test_vector_count_mismatch_raises_embedding_error(monkeypatch):
    monkeypatch.setattr(FastEmbedProvider, "_model", StubModel(drop=1))
    with pytest.raises(EmbeddingError, match="expected 3 vectors, got 2"):
        await FastEmbedProvider().embed_passages(["a", "b", "c"])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_vector_raises_embedding_error(monkeypatch, bad):
    monkeypatch.setattr(FastEmbedProvider, "_model", StubModel(bad_value=bad))
    with pytest.raises(EmbeddingError, match="NaN or infinity"):
        await FastEmbedProvider().embed_passages(["a"])
