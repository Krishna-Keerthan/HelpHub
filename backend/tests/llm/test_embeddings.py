import numpy as np
import pytest
from sqlalchemy import text

from app.services.embeddings import (
    FastEmbedProvider,
    get_embedding,
    get_embeddings_batch,
)

EMBEDDING_DIM = 384

# Tests that load the real model are marked slow: first use downloads it.
# Run them with `uv run pytest -m slow`.


@pytest.mark.slow
def test_embedding_dimensions_and_norm():
    text = "Verify embedding vector dimensions and unit length."
    vector = get_embedding(text)

    assert len(vector) == EMBEDDING_DIM

    # Vectors are unit length (L2 norm == 1.0)
    norm = np.linalg.norm(vector)
    assert pytest.approx(norm, rel=1e-5) == 1.0


@pytest.mark.slow
def test_single_vs_batch_consistency():
    text = "Batch versus single text consistency check."
    single_vec = get_embedding(text)
    batch_vecs = get_embeddings_batch([text])

    assert len(batch_vecs) == 1
    np.testing.assert_allclose(single_vec, batch_vecs[0], atol=1e-6)


@pytest.mark.slow
def test_semantic_similarity_ranking():
    q = "How do I reset my password?"
    target_match = "Steps to change your account password"
    distractor = "Quarterly revenue grew 12%"

    v_q = np.array(get_embedding(q))
    v_target = np.array(get_embedding(target_match))
    v_distractor = np.array(get_embedding(distractor))

    sim_target = np.dot(v_q, v_target)
    sim_distractor = np.dot(v_q, v_distractor)

    assert sim_target > sim_distractor


@pytest.mark.slow
def test_max_size_chunk_embeds():
    max_chunk = "a" * 1024  # Assuming max chunk limit
    vector = get_embedding(max_chunk)
    assert len(vector) == EMBEDDING_DIM


@pytest.mark.asyncio
async def test_provider_matches_db_column_dimension(owner_conn):
    """Provider's dimension equals the DB column's dimension."""
    result = await owner_conn.execute(
        text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        )
    )
    assert result.scalar_one() == f"vector({FastEmbedProvider.dim})"
    assert FastEmbedProvider.dim == EMBEDDING_DIM
