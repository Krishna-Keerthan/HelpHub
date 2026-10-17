"""The exact fallback never uses HNSW; search statements are tenant-bound."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.repositories.chunks import (
    CHUNKS_EMBEDDING_INDEX,
    TENANT_FILTER,
    SearchQuery,
    search_statement,
)
from app.db.repositories.documents import titles_statement
from app.db.tenant_context import set_tenant
from tests.conftest import SeededTenant, insert_chunks, insert_document, unit_vector
from tests.helpers.plans import explain_statement


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
            explain_statement(
                search_statement(
                    tenant["id"], SearchQuery(unit_vector(1.0), "", (), 3), exact=True
                )
            )
        )
        plan_text = "\n".join(row[0] for row in plan)

    assert CHUNKS_EMBEDDING_INDEX not in plan_text, plan_text


@pytest.mark.parametrize("exact", [False, True])
def test_search_statement_binds_tenant_in_every_branch(exact: bool) -> None:
    tid = uuid.uuid4()
    statement = search_statement(
        tid, SearchQuery(unit_vector(1.0), "reset", ("E-4012",), 3), exact=exact
    )
    # Vector branch, full-text branch and the final join each carry the filter,
    # and nothing else compares tenant_id.
    assert statement.text.count(TENANT_FILTER) == 3
    assert statement.text.count("tenant_id") == 3
    assert "AS MATERIALIZED" in statement.text
    params = statement.compile().params
    assert params["tid"] == tid
    assert params["k"] == 3
    assert params["words"] == "reset"
    assert params["code0"] == '"E-4012"'


def test_titles_statement_binds_tenant() -> None:
    tid = uuid.uuid4()
    doc_ids = [uuid.uuid4(), uuid.uuid4()]
    compiled = titles_statement(tid, doc_ids).compile()
    assert "tenant_id" in str(compiled)
    assert tid in compiled.params.values()
