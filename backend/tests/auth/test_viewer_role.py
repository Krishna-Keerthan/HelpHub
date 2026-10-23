"""A viewer is read-only: search, list and chat work; every other write is 403."""

import pytest
from httpx import AsyncClient

from tests.conftest import MakeTenant, auth_headers
from tests.helpers.fakes import FakeLLMProvider
from tests.helpers.ingestion_helpers import CONTENT

JSON_DOC = {"title": "Doc", "content": CONTENT}


async def test_viewer_can_search_list_and_chat(
    client: AsyncClient, make_tenant: MakeTenant, fake_llm: FakeLLMProvider
) -> None:
    viewer = await make_tenant(role="viewer")
    headers = auth_headers(viewer)
    fake_llm.tokens = ["ok"]

    search = await client.post("/search", json={"query": "reset"}, headers=headers)
    listed = await client.get("/documents", headers=headers)
    me = await client.get("/auth/me", headers=headers)
    chat = await client.post("/chat/stream", json={"message": "hi"}, headers=headers)

    assert search.status_code == 200
    assert listed.status_code == 200
    assert me.status_code == 200 and me.json()["role"] == "viewer"
    assert chat.status_code == 200
    conversations = await client.get("/conversations", headers=headers)
    assert conversations.status_code == 200 and len(conversations.json()) == 1


async def test_viewer_cannot_create_or_upload_documents(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    headers = auth_headers(await make_tenant(role="viewer"))
    created = await client.post("/documents", json=JSON_DOC, headers=headers)
    uploaded = await client.post(
        "/documents/upload",
        files={"file": ("a.md", CONTENT.encode(), "text/markdown")},
        headers=headers,
    )
    assert created.status_code == 403
    assert uploaded.status_code == 403
    assert (await client.get("/documents", headers=headers)).json() == []


async def test_viewer_cannot_delete_or_create_users(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    admin = await make_tenant(role="admin")
    doc = await client.post("/documents", json=JSON_DOC, headers=auth_headers(admin))
    doc_id = doc.json()["id"]
    viewer = await make_tenant(role="viewer")
    headers = auth_headers(viewer)
    deleted = await client.delete(f"/documents/{doc_id}", headers=headers)
    new_user = await client.post(
        "/users",
        json={"email": "x@example.com", "password": "correct-horse-battery"},
        headers=headers,
    )
    assert deleted.status_code == 403
    assert new_user.status_code == 403
    still_there = await client.get(f"/documents/{doc_id}", headers=auth_headers(admin))
    assert still_there.status_code == 200


@pytest.mark.parametrize("role", ["admin", "agent"])
async def test_admin_and_agent_can_still_upload(
    client: AsyncClient, make_tenant: MakeTenant, role: str
) -> None:
    headers = auth_headers(await make_tenant(role=role))
    created = await client.post("/documents", json=JSON_DOC, headers=headers)
    uploaded = await client.post(
        "/documents/upload",
        files={"file": ("a.md", CONTENT.encode(), "text/markdown")},
        headers=headers,
    )
    assert created.status_code == 201
    assert uploaded.status_code in (200, 201)
