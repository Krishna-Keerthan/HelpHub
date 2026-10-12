"""hydrate_chunks filters on tenant_id explicitly *and* relies on RLS."""

import uuid

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.repositories import chunks as chunks_repo
from app.db.tenant_context import tenant_transaction
from tests.conftest import MakeTenant
from tests.helpers.es_helpers import upload
from tests.helpers.ingestion_helpers import owner_chunks


def test_hydration_statement_has_an_explicit_tenant_predicate() -> None:
    sql = str(
        chunks_repo.hydrate_statement(uuid.uuid4(), [uuid.uuid4()]).compile(
            dialect=postgresql.dialect()
        )
    )
    assert "chunks.tenant_id =" in sql


async def test_explicit_filter_holds_even_when_the_session_is_scoped_to_the_owner(
    client, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    """Session scoped to B (RLS would allow B's rows) but the call names A:
    only the explicit tenant_id predicate can drop the row."""
    a, b = await make_tenant(), await make_tenant()
    doc_b = await upload(client, b, "B doc", "Some text of tenant B.")
    chunk_ids = [r["id"] for r in await owner_chunks(owner_conn, doc_b)]

    async with tenant_transaction(b["id"]) as session:
        assert await chunks_repo.hydrate_chunks(session, a["id"], chunk_ids) == []
        assert len(
            await chunks_repo.hydrate_chunks(session, b["id"], chunk_ids)
        ) == len(chunk_ids)


async def test_rls_alone_hides_foreign_chunks(
    client, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    doc_b = await upload(client, b, "B doc", "Some text of tenant B.")
    chunk_ids = [r["id"] for r in await owner_chunks(owner_conn, doc_b)]

    async with tenant_transaction(a["id"]) as session:
        assert await chunks_repo.hydrate_chunks(session, b["id"], chunk_ids) == []


async def test_rows_follow_the_given_order_and_unknown_ids_are_dropped(
    client, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a = await make_tenant()
    long_text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(8))
    doc = await upload(client, a, "Doc", long_text)
    ids = [r["id"] for r in await owner_chunks(owner_conn, doc)]
    assert len(ids) >= 3
    wanted = [ids[2], uuid.uuid4(), ids[0], ids[1]]

    async with tenant_transaction(a["id"]) as session:
        rows = await chunks_repo.hydrate_chunks(session, a["id"], wanted)

    assert [r.id for r in rows] == [ids[2], ids[0], ids[1]]
