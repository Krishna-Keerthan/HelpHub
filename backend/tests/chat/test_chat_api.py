"""POST /chat/stream, GET /conversations, GET /conversations/{id}/messages.

How these tests read the stream: the streams are finite, so ``client.post``
(httpx ASGITransport) returns the whole body once the generator finishes and
the SSE text is parsed afterwards. ASGITransport may buffer, so it cannot show
event timing or a client disconnect; those are tested on the orchestrator
generator directly (tests/test_chat_service.py: cancel the consuming task,
aclose()).
"""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import get_embedding_provider
from app.core.config import settings
from app.main import app
from app.services.chat import REFUSAL_TEXT
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.helpers.chat_helpers import (
    AxisQueryEmbedder,
    BrokenEmbedder,
    checked_out_connections,
    message_rows,
    seed_chunk,
)
from tests.helpers.fakes import FakeLLMProvider
from tests.helpers.ingestion_helpers import idle_in_transaction

TOKENS = ["Use ", "Settings ", "[1]."]


@pytest.fixture(autouse=True)
def chat_setup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "min_retrieval_score", 0.6)
    app.dependency_overrides[get_embedding_provider] = AxisQueryEmbedder
    # conftest's autouse fixture restores the previous override afterwards.
    yield


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name is not None:
            events.append((name, data))
    return events


async def stream(client: AsyncClient, tenant: SeededTenant, payload: dict, **kw):
    return await client.post(
        "/chat/stream", json=payload, headers=auth_headers(tenant), **kw
    )


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/chat/stream", json={"message": "hi"})
    assert response.status_code == 401


async def test_happy_path_streams_sources_tokens_done(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    fake_llm: FakeLLMProvider,
) -> None:
    tenant = await make_tenant()
    chunk_id = await seed_chunk(owner_conn, tenant)
    fake_llm.tokens = TOKENS
    response = await stream(client, tenant, {"message": "how do I reset?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["sources"] + ["token"] * 3 + ["done"]
    sources = events[0][1]
    assert [s["chunk_id"] for s in sources["sources"]] == [str(chunk_id)]
    assert [data["text"] for name, data in events if name == "token"] == TOKENS
    done = events[-1][1]
    assert done["status"] == "complete" and done["cited"] == [1]
    conversation_id = done["conversation_id"]
    assert sources["conversation_id"] == conversation_id
    rows = await message_rows(owner_conn, tenant["id"])
    assert [str(r["conversation_id"]) for r in rows] == [conversation_id] * 2


async def test_below_threshold_streams_the_refusal(
    client: AsyncClient,
    make_tenant: MakeTenant,
    fake_llm: FakeLLMProvider,
) -> None:
    tenant = await make_tenant()
    events = parse_sse((await stream(client, tenant, {"message": "anything"})).text)
    assert [n for n, _ in events] == ["sources", "token", "done"]
    assert events[0][1]["sources"] == []
    assert events[1][1]["text"] == REFUSAL_TEXT
    assert events[2][1]["status"] == "no_answer"
    assert fake_llm.calls == 0


async def test_llm_failure_is_a_generic_error_event(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    fake_llm: FakeLLMProvider,
) -> None:
    tenant = await make_tenant()
    await seed_chunk(owner_conn, tenant)
    # gate-allow: secret fake value used only by this test
    secret = "PROVIDER-SECRET-TEXT"
    fake_llm.tokens, fake_llm.fail_at, fake_llm.error = TOKENS, 1, RuntimeError(secret)
    response = await stream(client, tenant, {"message": "q"})
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "internal_error"
    assert secret not in response.text
    assert "done" not in [n for n, _ in events]


async def test_embedding_failure_is_a_generic_error_event(
    client: AsyncClient, make_tenant: MakeTenant, fake_llm: FakeLLMProvider
) -> None:
    app.dependency_overrides[get_embedding_provider] = BrokenEmbedder
    tenant = await make_tenant()
    response = await stream(client, tenant, {"message": "q"})
    assert [n for n, _ in parse_sse(response.text)] == ["error"]
    assert "EMBED-SECRET-TEXT" not in response.text
    assert fake_llm.calls == 0


async def test_no_transaction_or_connection_is_held_while_the_model_streams(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    make_tenant: MakeTenant,
    fake_llm: FakeLLMProvider,
) -> None:
    tenant = await make_tenant()
    await seed_chunk(owner_conn, tenant)
    observed: list[tuple[int, int]] = []

    async def probe(_: int) -> None:
        observed.append(
            (checked_out_connections(), await idle_in_transaction(owner_conn))
        )

    fake_llm.tokens, fake_llm.on_token = TOKENS, probe
    response = await stream(client, tenant, {"message": "q"})
    assert response.status_code == 200
    assert observed == [(0, 0)] * len(TOKENS)


async def second_user_headers(
    owner_conn: AsyncConnection, tenant: SeededTenant
) -> dict[str, str]:
    user_id = (
        await owner_conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, password_hash, role, is_active) "
                "VALUES (:t, :e, 'x', 'agent', true) RETURNING id"
            ),
            {"t": tenant["id"], "e": f"two@{tenant['slug']}.example.com"},
        )
    ).scalar_one()
    await owner_conn.commit()
    return auth_headers({**tenant, "user_id": user_id})


async def start_conversation(client, tenant) -> str:
    events = parse_sse((await stream(client, tenant, {"message": "first"})).text)
    return events[-1][1]["conversation_id"]


async def test_unknown_conversation_is_a_real_404_not_a_stream(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await stream(
        client, tenant, {"message": "q", "conversation_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Conversation not found"}
    assert await message_rows(owner_conn, tenant["id"]) == []


async def test_other_users_and_other_tenants_conversations_are_404(
    client: AsyncClient, owner_conn: AsyncConnection, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    conversation_id = await start_conversation(client, a)
    same_tenant_headers = await second_user_headers(owner_conn, a)
    payload = {"message": "steal", "conversation_id": conversation_id}
    for headers in (same_tenant_headers, auth_headers(b)):
        response = await client.post("/chat/stream", json=payload, headers=headers)
        assert response.status_code == 404
        listing = await client.get(
            f"/conversations/{conversation_id}/messages", headers=headers
        )
        assert listing.status_code == 404
    assert len(await message_rows(owner_conn, a["id"])) == 2
    assert await message_rows(owner_conn, b["id"]) == []
