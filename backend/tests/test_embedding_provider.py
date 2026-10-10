import numpy as np
import pytest

from app.api.deps import get_embedding_provider
from app.main import app
from app.services.embeddings import (
    FakeEmbeddingProvider,
    FastEmbedProvider,
    get_embedding,
)


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
    # The async and sync paths agree on passage embeddings.
    np.testing.assert_allclose(
        related, get_embedding("Steps to change your account password"), atol=1e-6
    )
