"""The exact fallback never uses HNSW; search statements are tenant-bound."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.repositories.chunks import (
    CHUNKS_EMBEDDING_INDEX,
    exact_search_statement,
    explain_statement,
)
from app.db.repositories.documents import titles_statement
from app.db.tenant_context import set_tenant
from tests.conftest import SeededTenant, insert_chunks, insert_document, unit_vector


@pytest.mark.parametrize(
    "flags",
    [(), ("enable_seqscan",), ("enable_sort",), ("enable_seqscan", "enable_sort")],
    ids=lambda f: "+".join(f) or "no-flags",
)
async def test_exact_search_plan_never_uses_hnsw(
    owner_conn: AsyncConnection,
    make_tenant,
    app_conn: AsyncConnection,
    flags: tuple[str, ...],
) -> None:
    tenant: SeededTenant = await make_tenant()
    doc = await insert_document(owner_conn, tenant["id"], created_by=tenant["user_id"])
    await insert_chunks(
        owner_conn, tenant["id"], doc, [unit_vector(1.0, 0.01 * i) for i in range(20)]
    )
    await owner_conn.commit()

    async with AsyncSession(bind=app_conn) as session:
        await set_tenant(session, tenant["id"])
        for flag in flags:
            await session.execute(text(f"SET LOCAL {flag} = off"))
        plan = await session.execute(
            explain_statement(exact_search_statement(tenant["id"], unit_vector(1.0), 3))
        )
        plan_text = "\n".join(row[0] for row in plan)

    assert CHUNKS_EMBEDDING_INDEX not in plan_text, plan_text


def test_exact_search_statement_binds_tenant() -> None:
    tid = uuid.uuid4()
    statement = exact_search_statement(tid, unit_vector(1.0), 3)
    assert "WHERE tenant_id = :tid" in statement.text
    assert "AS MATERIALIZED" in statement.text
    params = statement.compile().params
    assert params["tid"] == tid
    assert params["k"] == 3


def test_titles_statement_binds_tenant() -> None:
    tid = uuid.uuid4()
    doc_ids = [uuid.uuid4(), uuid.uuid4()]
    compiled = titles_statement(tid, doc_ids).compile()
    assert "tenant_id" in str(compiled)
    assert tid in compiled.params.values()
