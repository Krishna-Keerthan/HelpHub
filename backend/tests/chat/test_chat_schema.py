"""conversations / chat_messages: names, checks, composite FKs, cascade, seq."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import MakeTenant

CONSTRAINTS = [
    ("conversations", "fk_conversations_tenant_id_tenants"),
    ("conversations", "fk_conversations_tenant_id_users"),
    ("conversations", "uq_conversations_tenant_id_id"),
    ("chat_messages", "fk_chat_messages_tenant_id_tenants"),
    ("chat_messages", "fk_chat_messages_tenant_id_conversations"),
    ("chat_messages", "ck_chat_messages_role"),
    ("chat_messages", "ck_chat_messages_status"),
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
    assert result.scalar_one_or_none() == 1


async def _conversation(conn: AsyncConnection, tenant) -> uuid.UUID:
    return (
        await conn.execute(
            text(
                "INSERT INTO conversations (tenant_id, user_id) "
                "VALUES (:t, :u) RETURNING id"
            ),
            {"t": tenant["id"], "u": tenant["user_id"]},
        )
    ).scalar_one()


async def _message(conn, tenant, conversation_id, role="user", status="complete"):
    return (
        await conn.execute(
            text(
                "INSERT INTO chat_messages "
                "(tenant_id, conversation_id, role, content, status) "
                "VALUES (:t, :c, :r, 'x', :s) RETURNING id"
            ),
            {"t": tenant["id"], "c": conversation_id, "r": role, "s": status},
        )
    ).scalar_one()


async def test_messages_cascade_with_conversation_and_default_sources(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conv = await _conversation(owner_conn, tenant)
    message_id = await _message(owner_conn, tenant, conv)
    sources = (
        await owner_conn.execute(
            text("SELECT sources FROM chat_messages WHERE id = :i"), {"i": message_id}
        )
    ).scalar_one()
    assert sources == []
    await owner_conn.execute(
        text("DELETE FROM conversations WHERE id = :c"), {"c": conv}
    )
    left = (
        await owner_conn.execute(
            text("SELECT count(*) FROM chat_messages WHERE id = :i"), {"i": message_id}
        )
    ).scalar_one()
    await owner_conn.rollback()
    assert left == 0


@pytest.mark.parametrize(
    ("role", "status"), [("system", "complete"), ("user", "bogus")]
)
async def test_role_and_status_checks_reject_bad_values(
    owner_conn: AsyncConnection, make_tenant: MakeTenant, role: str, status: str
) -> None:
    tenant = await make_tenant()
    conv = await _conversation(owner_conn, tenant)
    with pytest.raises(IntegrityError):
        await _message(owner_conn, tenant, conv, role=role, status=status)
    await owner_conn.rollback()


async def test_composite_fks_reject_cross_tenant_links(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    conv_a = await _conversation(owner_conn, a)
    await owner_conn.commit()
    with pytest.raises(IntegrityError):  # B's tenant_id with A's conversation
        await _message(owner_conn, b, conv_a)
    await owner_conn.rollback()
    with pytest.raises(IntegrityError):  # A's tenant with B's user
        await owner_conn.execute(
            text("INSERT INTO conversations (tenant_id, user_id) VALUES (:t, :u)"),
            {"t": a["id"], "u": b["user_id"]},
        )
    await owner_conn.rollback()


async def test_seq_follows_insert_order_within_one_transaction(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conv = await _conversation(owner_conn, tenant)
    ids = [await _message(owner_conn, tenant, conv) for _ in range(5)]
    ordered = (
        (
            await owner_conn.execute(
                text(
                    "SELECT id FROM chat_messages WHERE conversation_id = :c ORDER BY seq"
                ),
                {"c": conv},
            )
        )
        .scalars()
        .all()
    )
    await owner_conn.rollback()
    assert list(ordered) == ids


async def test_seq_cannot_be_set_explicitly(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    conv = await _conversation(owner_conn, tenant)
    with pytest.raises(DBAPIError):
        await owner_conn.execute(
            text(
                "INSERT INTO chat_messages (tenant_id, conversation_id, role, "
                "content, status, seq) VALUES (:t, :c, 'user', 'x', 'complete', 1)"
            ),
            {"t": tenant["id"], "c": conv},
        )
    await owner_conn.rollback()


async def test_runtime_role_sees_only_own_tenant_conversations(
    owner_conn: AsyncConnection, app_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    await _conversation(owner_conn, a)
    await _conversation(owner_conn, b)
    await owner_conn.commit()
    await app_conn.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(a["id"])}
    )
    seen = (
        (await app_conn.execute(text("SELECT DISTINCT tenant_id FROM conversations")))
        .scalars()
        .all()
    )
    assert list(seen) == [a["id"]]
