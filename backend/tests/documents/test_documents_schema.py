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
