"""Conversation / message repositories: ownership filters and ordering."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.pagination import Page
from app.db.repositories import chat_messages as messages_repo
from app.db.repositories import conversations as conversations_repo
from app.db.repositories.chat_messages import NewMessage
from app.db.repositories.conversations import ConversationNotOwned
from app.db.tenant_context import tenant_transaction
from tests.conftest import MakeTenant


async def second_user(owner_conn: AsyncConnection, tenant) -> uuid.UUID:
    user_id = (
        await owner_conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, password_hash, role, is_active) "
                "VALUES (:t, :e, 'x', 'agent', true) RETURNING id"
            ),
            {"t": tenant["id"], "e": f"second@{tenant['slug']}.example.com"},
        )
    ).scalar_one()
    await owner_conn.commit()
    return user_id


async def test_get_owned_filters_by_user_and_tenant(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    other_user = await second_user(owner_conn, a)
    async with tenant_transaction(a["id"]) as session:
        conv = await conversations_repo.create(session, a["id"], a["user_id"])
    async with tenant_transaction(a["id"]) as session:
        mine = await conversations_repo.get_owned(
            session, a["id"], a["user_id"], conv.id
        )
        same_tenant_other_user = await conversations_repo.get_owned(
            session, a["id"], other_user, conv.id
        )
    async with tenant_transaction(b["id"]) as session:
        other_tenant = await conversations_repo.get_owned(
            session, b["id"], b["user_id"], conv.id
        )
    assert mine is not None
    assert same_tenant_other_user is None  # RLS alone would allow this
    assert other_tenant is None


async def test_list_for_user_returns_only_own_newest_first(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a = await make_tenant()
    other_user = await second_user(owner_conn, a)
    async with tenant_transaction(a["id"]) as session:
        first = await conversations_repo.create(session, a["id"], a["user_id"])
        await conversations_repo.create(session, a["id"], other_user)
    async with tenant_transaction(a["id"]) as session:
        second = await conversations_repo.create(session, a["id"], a["user_id"])
    async with tenant_transaction(a["id"]) as session:
        listed = await conversations_repo.list_for_user(
            session, a["id"], a["user_id"], limit=10, offset=0
        )
    assert [c.id for c in listed] == [second.id, first.id]
    assert all(c.user_id == a["user_id"] for c in listed)


async def test_history_is_in_insert_order_and_skips_unhelpful_assistant_rows(
    make_tenant: MakeTenant,
) -> None:
    a = await make_tenant()
    async with tenant_transaction(a["id"]) as session:
        conv = await conversations_repo.create(session, a["id"], a["user_id"])
        for role, status, content in [
            ("user", "complete", "q1"),
            ("assistant", "complete", "a1"),
            ("user", "complete", "q2"),
            ("assistant", "no_answer", "refusal"),
            ("user", "complete", "q3"),
            ("assistant", "failed", "partial"),
            ("user", "complete", "q4"),
        ]:
            await messages_repo.add(
                session,
                a["id"],
                a["user_id"],
                conv.id,
                NewMessage(role=role, content=content, status=status),
            )
    async with tenant_transaction(a["id"]) as session:
        history = await messages_repo.recent_history(
            session, a["id"], a["user_id"], conv.id, 4
        )
        everything = await messages_repo.list_for_conversation(
            session, a["id"], a["user_id"], conv.id, Page(50)
        )
    # q1 a1 q2 q3 q4 qualify (refusal and failed rows do not); the last 4 remain.
    assert [m.content for m in history] == ["a1", "q2", "q3", "q4"]
    assert [m.content for m in everything] == [
        "q1",
        "a1",
        "q2",
        "refusal",
        "q3",
        "partial",
        "q4",
    ]


async def seeded_conversation(owner_conn: AsyncConnection, make_tenant: MakeTenant):
    """(tenant a, a's second user, tenant b, a's conversation with 2 messages)."""
    a, b = await make_tenant(), await make_tenant()
    other_user = await second_user(owner_conn, a)
    async with tenant_transaction(a["id"]) as session:
        conv = await conversations_repo.create(session, a["id"], a["user_id"])
        for role in ("user", "assistant"):
            await messages_repo.add(
                session,
                a["id"],
                a["user_id"],
                conv.id,
                NewMessage(role=role, content=f"{role} text", status="complete"),
            )
    return a, other_user, b, conv


async def test_message_reads_return_nothing_for_other_users_and_tenants(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, other_user, b, conv = await seeded_conversation(owner_conn, make_tenant)
    async with tenant_transaction(a["id"]) as session:
        own = await messages_repo.recent_history(
            session, a["id"], a["user_id"], conv.id, 10
        )
        foreign_user_history = await messages_repo.recent_history(
            session, a["id"], other_user, conv.id, 10
        )
        foreign_user_list = await messages_repo.list_for_conversation(
            session, a["id"], other_user, conv.id, Page(10)
        )
    async with tenant_transaction(b["id"]) as session:
        foreign_tenant_history = await messages_repo.recent_history(
            session, b["id"], b["user_id"], conv.id, 10
        )
        foreign_tenant_list = await messages_repo.list_for_conversation(
            session, b["id"], b["user_id"], conv.id, Page(10)
        )
    assert len(own) == 2
    assert foreign_user_history == [] and foreign_user_list == []
    assert foreign_tenant_history == [] and foreign_tenant_list == []


async def test_touch_affects_only_the_owners_conversation(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, other_user, b, conv = await seeded_conversation(owner_conn, make_tenant)
    async with tenant_transaction(a["id"]) as session:
        by_other_user = await conversations_repo.touch(
            session, a["id"], other_user, conv.id
        )
    async with tenant_transaction(b["id"]) as session:
        by_other_tenant = await conversations_repo.touch(
            session, b["id"], b["user_id"], conv.id
        )
    async with tenant_transaction(a["id"]) as session:
        by_owner = await conversations_repo.touch(
            session, a["id"], a["user_id"], conv.id
        )
    assert (by_other_user, by_other_tenant, by_owner) == (0, 0, 1)


async def test_add_refuses_a_conversation_the_user_does_not_own(
    owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, other_user, b, conv = await seeded_conversation(owner_conn, make_tenant)
    for tenant_id, user_id in ((a["id"], other_user), (b["id"], b["user_id"])):
        with pytest.raises(ConversationNotOwned):
            async with tenant_transaction(tenant_id) as session:
                await messages_repo.add(
                    session,
                    tenant_id,
                    user_id,
                    conv.id,
                    NewMessage(role="user", content="injected", status="complete"),
                )
    count = (
        await owner_conn.execute(
            text("SELECT count(*) FROM chat_messages WHERE conversation_id = :c"),
            {"c": conv.id},
        )
    ).scalar_one()
    await owner_conn.rollback()
    assert count == 2
