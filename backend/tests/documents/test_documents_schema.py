import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import (
    constraint_name,
    insert_chunk,
    insert_document,
    sqlstate,
    unit_vector,
)


@pytest.mark.asyncio
async def test_composite_fk_tenant_mismatch_rejected(owner_conn, two_tenants_seeded):
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]

    # Create document under Tenant B
    doc_b_id = await insert_document(
        owner_conn, tb["id"], created_by=tb["user_id"], title="Doc B"
    )
    await owner_conn.commit()

    # Attempt inserting chunk with Tenant A's tenant_id and Tenant B's document_id
    with pytest.raises(DBAPIError) as exc_info:
        await insert_chunk(owner_conn, ta["id"], doc_b_id)
    await owner_conn.rollback()

    # SQLSTATE 23503 = foreign_key_violation, raised by the composite FK
    assert sqlstate(exc_info.value) == "23503"
    assert constraint_name(exc_info.value) == "fk_chunks_tenant_id_documents"


@pytest.mark.asyncio
async def test_content_hash_uniqueness_per_tenant(owner_conn, two_tenants_seeded):
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]
    content_hash = "hash_abc123"

    # Same content hash in two different tenants succeeds
    await insert_document(
        owner_conn,
        ta["id"],
        created_by=ta["user_id"],
        title="Doc 1",
        content_hash=content_hash,
    )
    await insert_document(
        owner_conn,
        tb["id"],
        created_by=tb["user_id"],
        title="Doc 2",
        content_hash=content_hash,
    )
    await owner_conn.commit()

    # Twice in one tenant fails on the named unique constraint
    with pytest.raises(DBAPIError) as exc_info:
        await insert_document(
            owner_conn,
            ta["id"],
            created_by=ta["user_id"],
            title="Doc 3",
            content_hash=content_hash,
        )
    await owner_conn.rollback()

    assert "unique" in str(exc_info.value).lower()
    assert sqlstate(exc_info.value) == "23505"
    assert constraint_name(exc_info.value) == "uq_documents_tenant_id_content_hash"


@pytest.mark.asyncio
async def test_invalid_vector_dimension_rejected(owner_conn, two_tenants_seeded):
    ta = two_tenants_seeded["tenant_a"]
    doc_id = await insert_document(
        owner_conn, ta["id"], created_by=ta["user_id"], title="Doc A"
    )
    await owner_conn.commit()

    # 3-dimension vector rejected by the vector(384) column. dim=None disables
    # the client-side length check so the database does the rejecting.
    with pytest.raises(DBAPIError) as exc_info:
        await insert_chunk(
            owner_conn, ta["id"], doc_id, embedding=[0.1, 0.2, 0.3], dim=None
        )
    await owner_conn.rollback()

    # SQLSTATE 22000 = data_exception ("expected 384 dimensions, not 3")
    assert sqlstate(exc_info.value) == "22000"
    assert "384" in str(exc_info.value)


@pytest.mark.asyncio
async def test_tenant_deletion_cascade(owner_conn, two_tenants_seeded):
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]
    # Add doc and chunk for A, and a doc and chunk for B that must survive
    doc_id = await insert_document(owner_conn, ta["id"], created_by=ta["user_id"])
    await insert_chunk(owner_conn, ta["id"], doc_id, embedding=unit_vector(1.0))
    doc_b_id = await insert_document(owner_conn, tb["id"], created_by=tb["user_id"])
    await insert_chunk(owner_conn, tb["id"], doc_b_id, embedding=unit_vector(1.0))
    await owner_conn.commit()

    for table in ("documents", "chunks"):
        res = await owner_conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tid"),
            {"tid": ta["id"]},
        )
        assert res.scalar_one() == 1, f"{table} not seeded"

    # Deleting tenant works and cascades to documents and chunks
    await owner_conn.execute(
        text("DELETE FROM tenants WHERE id = :tid"), {"tid": ta["id"]}
    )
    await owner_conn.commit()

    for table in ("documents", "chunks"):
        res = await owner_conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tid"),
            {"tid": ta["id"]},
        )
        assert res.scalar_one() == 0, f"{table} rows survived tenant deletion"
        res = await owner_conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tid"),
            {"tid": tb["id"]},
        )
        assert res.scalar_one() == 1, f"{table} of another tenant was deleted"


@pytest.mark.asyncio
async def test_hnsw_index_exists_with_cosine(owner_conn):
    query = text("""
        SELECT indexdef FROM pg_indexes
        WHERE tablename = 'chunks' AND indexdef LIKE '%hnsw%vector_cosine_ops%';
    """)
    res = await owner_conn.execute(query)
    indexdef = res.scalar_one_or_none()
    assert indexdef is not None
    # Build parameters match the model/migration declaration.
    assert "m='16'" in indexdef
    assert "ef_construction='64'" in indexdef
