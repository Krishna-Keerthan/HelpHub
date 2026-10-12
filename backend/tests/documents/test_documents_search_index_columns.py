"""Migration 0007: documents.search_index_status / search_index_error."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import MakeTenant, constraint_name
from tests.helpers.es_helpers import doc_index_state


async def _insert(
    owner_conn: AsyncConnection, tenant_id: uuid.UUID, **extra
) -> uuid.UUID:
    doc_id = uuid.uuid4()
    columns = ["id", "tenant_id", "title", "raw_text", "content_hash", *extra]
    values = [":id", ":tid", "'t'", "'x'", ":hash", *(f":{k}" for k in extra)]
    await owner_conn.execute(
        text(
            f"INSERT INTO documents ({', '.join(columns)}) VALUES ({', '.join(values)})"
        ),
        {"id": doc_id, "tid": tenant_id, "hash": uuid.uuid4().hex * 2, **extra},
    )
    await owner_conn.commit()
    return doc_id


async def test_default_is_pending_and_error_is_null(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc_id = await _insert(owner_conn, tenant["id"])
    state = await doc_index_state(owner_conn, doc_id)
    assert state["search_index_status"] == "PENDING"
    assert state["search_index_error"] is None


@pytest.mark.parametrize("value", ["PENDING", "INDEXED", "FAILED"])
async def test_allowed_values(
    owner_conn: AsyncConnection, make_tenant: MakeTenant, value: str
) -> None:
    tenant = await make_tenant()
    doc_id = await _insert(owner_conn, tenant["id"], search_index_status=value)
    assert (await doc_index_state(owner_conn, doc_id))["search_index_status"] == value


@pytest.mark.parametrize("value", ["READY", "indexed", "", "DONE"])
async def test_other_values_violate_the_check(
    owner_conn: AsyncConnection, make_tenant: MakeTenant, value: str
) -> None:
    tenant = await make_tenant()
    with pytest.raises(IntegrityError) as info:
        await _insert(owner_conn, tenant["id"], search_index_status=value)
    await owner_conn.rollback()
    assert constraint_name(info.value) == "ck_documents_search_index_status"


async def test_column_is_not_null(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    doc_id = await _insert(owner_conn, tenant["id"])
    with pytest.raises(IntegrityError):
        await owner_conn.execute(
            text("UPDATE documents SET search_index_status = NULL WHERE id = :id"),
            {"id": doc_id},
        )
    await owner_conn.rollback()
