import asyncio
import time
from pathlib import Path

import numpy as np
import pytest

import app.main as main_module
from app.api.deps import get_embedding_provider
from app.core.config import settings
from app.main import app
from app.services import embeddings
from app.services.embeddings import (
    EMBED_BATCH_SIZE,
    EmbeddingError,
    FakeEmbeddingProvider,
    FastEmbedProvider,
)
from tests import conftest as conftest_module


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


def test_real_dependency_resolves_to_fastembed_without_loading_model(monkeypatch):
    monkeypatch.setattr(FastEmbedProvider, "_model", None)
    # Call the dependency itself: the autouse override only affects the app.
    provider = get_embedding_provider()
    assert isinstance(provider, FastEmbedProvider)
    assert provider.dim == 384
    assert provider.model_name == "BAAI/bge-small-en-v1.5"
    assert FastEmbedProvider._model is None  # nothing loaded by resolving it


def test_tests_override_the_dependency_with_the_fake():
    override = app.dependency_overrides[get_embedding_provider]
    assert isinstance(override(), FakeEmbeddingProvider)


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


@pytest.mark.slow
@pytest.mark.asyncio
async def test_real_async_embed_query_semantic_ranking():
    provider = FastEmbedProvider()
    query = await provider.embed_query("How do I reset my password?")
    related, unrelated = await provider.embed_passages(
        ["Steps to change your account password", "Quarterly revenue grew 12%"]
    )
    assert len(query) == provider.dim
    assert np.dot(query, related) > np.dot(query, unrelated)


async def test_lifespan_skips_warm_up_when_flag_is_false(monkeypatch):
    calls: list[str] = []

    async def fake_warm_up() -> None:
        calls.append("warm")

    monkeypatch.setattr(main_module, "warm_up_default_provider", fake_warm_up)
    monkeypatch.setattr(settings, "warm_up_embeddings", False)
    async with main_module.lifespan(app):
        pass
    assert calls == []

    monkeypatch.setattr(settings, "warm_up_embeddings", True)
    async with main_module.lifespan(app):
        pass
    assert calls == ["warm"]


def test_tests_run_with_warm_up_disabled():
    assert settings.warm_up_embeddings is False


def test_model_cache_dir_is_derived_from_file_location_not_cwd(monkeypatch, tmp_path):
    expected = Path(embeddings.__file__).resolve().parents[2] / ".cache" / "fastembed"
    monkeypatch.chdir(tmp_path)
    assert embeddings.MODEL_CACHE_DIR == expected
    assert embeddings.MODEL_CACHE_DIR.is_absolute()
    assert tmp_path not in embeddings.MODEL_CACHE_DIR.parents


def test_autouse_fixture_restores_a_previous_override():
    """Run the fixture body by hand: it must restore, not just pop, an override."""
    previous = lambda: "previous"
    body = conftest_module.fake_embedding_provider._get_wrapped_function()
    original = app.dependency_overrides[get_embedding_provider]
    try:
        app.dependency_overrides[get_embedding_provider] = previous
        gen = body()
        next(gen)
        assert app.dependency_overrides[get_embedding_provider] is FakeEmbeddingProvider
        with pytest.raises(StopIteration):
            next(gen)
        assert app.dependency_overrides[get_embedding_provider] is previous
    finally:
        app.dependency_overrides[get_embedding_provider] = original


async def test_embed_passages_batches_in_64s_and_returns_plain_floats(monkeypatch):
    stub = StubModel()
    monkeypatch.setattr(FastEmbedProvider, "_model", stub)
    texts = [f"text {i}" for i in range(130)]
    vectors = await FastEmbedProvider().embed_passages(texts)
    assert EMBED_BATCH_SIZE == 64
    assert stub.batch_sizes == [64, 64, 2]
    assert len(vectors) == 130
    assert all(type(x) is float for x in vectors[0])


async def test_embed_passages_empty_input_makes_no_model_call(monkeypatch):
    stub = StubModel()
    monkeypatch.setattr(FastEmbedProvider, "_model", stub)
    assert await FastEmbedProvider().embed_passages([]) == []
    assert stub.batch_sizes == []


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


@pytest.mark.slow
async def test_embedding_does_not_block_the_event_loop():
    provider = FastEmbedProvider()
    await provider.warm_up()  # model load is not what is being measured
    texts = [
        f"Document {i}: " + "reset your password in settings. " * 40 for i in range(64)
    ]
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    await asyncio.sleep(0)  # let the ticker start
    started = time.perf_counter()
    try:
        vectors = await provider.embed_passages(texts)
    finally:
        duration = time.perf_counter() - started
        task.cancel()
    assert len(vectors) == 64
    # A blocked loop ticks ~0 times; a free one ticks about duration / 0.01.
    expected = duration / 0.01
    assert expected >= 10, f"embedding too fast ({duration:.3f}s) to be meaningful"
    assert ticks >= 0.2 * expected, f"{ticks} ticks in {duration:.2f}s"
