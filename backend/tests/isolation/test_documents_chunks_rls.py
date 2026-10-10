import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import (
    ChunkMaker,
    DocumentMaker,
    SeededTenant,
    sqlstate,
    unit_vector,
)

RLS_VIOLATION = "42501"
SET_TENANT = "SELECT set_config('app.tenant_id', :tid, false)"

Tenants = dict[str, SeededTenant]


async def use_tenant(conn: AsyncConnection, tenant_id: uuid.UUID) -> None:
    """Session-level tenant context, committed so a later rollback keeps it."""
    await conn.execute(text(SET_TENANT), {"tid": str(tenant_id)})
    await conn.commit()


async def owner_value(
    owner_conn: AsyncConnection, table: str, column: str, row_id: uuid.UUID
) -> str | None:
    await owner_conn.rollback()  # fresh snapshot
    result = await owner_conn.execute(
        text(f"SELECT {column} FROM {table} WHERE id = :id"), {"id": row_id}
    )
    return result.scalar_one_or_none()


# --- documents ---------------------------------------------------------------


async def test_documents_insert_for_other_tenant_fails_rls(
    app_conn: AsyncConnection, two_tenants_seeded: Tenants
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    await use_tenant(app_conn, ta["id"])

    with pytest.raises(DBAPIError) as exc_info:
        await app_conn.execute(
            text(
                "INSERT INTO documents (tenant_id, title, raw_text, content_hash) "
                "VALUES (:tid, 'x', 'x', :hash)"
            ),
            {"tid": tb["id"], "hash": uuid.uuid4().hex},
        )
    assert sqlstate(exc_info.value) == RLS_VIOLATION


async def test_documents_update_other_tenant_affects_zero_rows(
    app_conn: AsyncConnection,
    owner_conn: AsyncConnection,
    two_tenants_seeded: Tenants,
    make_document: DocumentMaker,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_b = await make_document(tb, title="original")
    await use_tenant(app_conn, ta["id"])

    result = await app_conn.execute(
        text("UPDATE documents SET title = 'hacked' WHERE id = :id"), {"id": doc_b}
    )
    assert result.rowcount == 0
    await app_conn.commit()
    assert await owner_value(owner_conn, "documents", "title", doc_b) == "original"


async def test_documents_delete_other_tenant_affects_zero_rows(
    app_conn: AsyncConnection,
    owner_conn: AsyncConnection,
    two_tenants_seeded: Tenants,
    make_document: DocumentMaker,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_b = await make_document(tb, title="keep")
    await use_tenant(app_conn, ta["id"])

    result = await app_conn.execute(
        text("DELETE FROM documents WHERE id = :id"), {"id": doc_b}
    )
    assert result.rowcount == 0
    await app_conn.commit()
    assert await owner_value(owner_conn, "documents", "title", doc_b) == "keep"


async def test_documents_select_other_tenant_by_id_returns_nothing(
    app_conn: AsyncConnection,
    two_tenants_seeded: Tenants,
    make_document: DocumentMaker,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_b = await make_document(tb, title="b-only")
    select = text("SELECT title FROM documents WHERE id = :id")

    await use_tenant(app_conn, ta["id"])
    assert (await app_conn.execute(select, {"id": doc_b})).first() is None

    # Positive control: the row is there, and visible under B's own context.
    await use_tenant(app_conn, tb["id"])
    assert (await app_conn.execute(select, {"id": doc_b})).scalar_one() == "b-only"


# --- chunks ------------------------------------------------------------------


async def test_chunks_insert_for_other_tenant_fails_rls(
    app_conn: AsyncConnection,
    two_tenants_seeded: Tenants,
    make_document: DocumentMaker,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_b = await make_document(tb)
    await use_tenant(app_conn, ta["id"])

    with pytest.raises(DBAPIError) as exc_info:
        await app_conn.execute(
            text(
                "INSERT INTO chunks (tenant_id, document_id, chunk_index, text, "
                "char_start, char_end, embedding, embedding_model) "
                "VALUES (:tid, :doc, 0, 'x', 0, 1, :vec, 'm')"
            ),
            {
                "tid": tb["id"],
                "doc": doc_b,
                "vec": str(unit_vector(1.0)),
            },
        )
    assert sqlstate(exc_info.value) == RLS_VIOLATION


async def test_chunks_update_other_tenant_affects_zero_rows(
    app_conn: AsyncConnection,
    owner_conn: AsyncConnection,
    two_tenants_seeded: Tenants,
    make_document: DocumentMaker,
    make_chunk: ChunkMaker,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_b = await make_document(tb)
    chunk_b = await make_chunk(tb["id"], doc_b, content="original")
    await use_tenant(app_conn, ta["id"])

    result = await app_conn.execute(
        text("UPDATE chunks SET text = 'hacked' WHERE id = :id"), {"id": chunk_b}
    )
    assert result.rowcount == 0
    await app_conn.commit()
    assert await owner_value(owner_conn, "chunks", "text", chunk_b) == "original"


async def test_chunks_delete_other_tenant_affects_zero_rows(
    app_conn: AsyncConnection,
    owner_conn: AsyncConnection,
    two_tenants_seeded: Tenants,
    make_document: DocumentMaker,
    make_chunk: ChunkMaker,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_b = await make_document(tb)
    chunk_b = await make_chunk(tb["id"], doc_b, content="keep")
    await use_tenant(app_conn, ta["id"])

    result = await app_conn.execute(
        text("DELETE FROM chunks WHERE id = :id"), {"id": chunk_b}
    )
    assert result.rowcount == 0
    await app_conn.commit()
    assert await owner_value(owner_conn, "chunks", "text", chunk_b) == "keep"


async def test_chunks_select_other_tenant_by_id_returns_nothing(
    app_conn: AsyncConnection,
    two_tenants_seeded: Tenants,
    make_document: DocumentMaker,
    make_chunk: ChunkMaker,
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    doc_b = await make_document(tb)
    chunk_b = await make_chunk(tb["id"], doc_b, content="b-only")
    select = text("SELECT text FROM chunks WHERE id = :id")

    await use_tenant(app_conn, ta["id"])
    assert (await app_conn.execute(select, {"id": chunk_b})).first() is None

    # Positive control: the row is there, and visible under B's own context.
    await use_tenant(app_conn, tb["id"])
    assert (await app_conn.execute(select, {"id": chunk_b})).scalar_one() == "b-only"
