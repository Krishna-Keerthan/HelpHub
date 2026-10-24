import pytest
from sqlalchemy import text

from app.services.embeddings import (
    FastEmbedProvider,
)

EMBEDDING_DIM = 384

# Tests that load the real model are marked slow: first use downloads it.
# Run them with `uv run pytest -m slow`.


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
