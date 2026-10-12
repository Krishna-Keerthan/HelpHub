import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

CONSTRAINTS = [
    ("documents", "ck_documents_status"),
    ("chunks", "ck_chunks_char_range"),
    ("documents", "uq_documents_tenant_id_id"),
    ("documents", "uq_documents_tenant_id_content_hash"),
    ("documents", "fk_documents_tenant_id_tenants"),
    ("documents", "fk_documents_tenant_id_users"),
    ("chunks", "fk_chunks_tenant_id_tenants"),
    ("chunks", "fk_chunks_tenant_id_documents"),
    ("chunks", "uq_chunks_document_id_chunk_index"),
]


@pytest.mark.parametrize(("table", "name"), CONSTRAINTS)
async def test_constraint_exists_with_exact_name(
    owner_conn: AsyncConnection, table: str, name: str
) -> None:
    result = await owner_conn.execute(
        text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname = :name AND conrelid = CAST(:table AS regclass)"
        ),
        {"name": name, "table": f"public.{table}"},
    )
    assert result.scalar_one_or_none() == 1, f"{table} lacks constraint {name}"


async def test_hnsw_index_exists_with_exact_name(owner_conn: AsyncConnection) -> None:
    result = await owner_conn.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'chunks' "
            "AND indexname = 'ix_chunks_embedding_hnsw'"
        )
    )
    indexdef = result.scalar_one_or_none()
    assert indexdef is not None, "chunks lacks index ix_chunks_embedding_hnsw"
    assert "hnsw" in indexdef and "vector_cosine_ops" in indexdef
