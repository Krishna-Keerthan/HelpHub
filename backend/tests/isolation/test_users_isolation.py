import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.security import create_access_token
from app.main import app
from tests.conftest import SEED_PASSWORD, SeededTenant, sqlstate

# gate-allow: secret fake value used only by this test
NEW_PASSWORD = "Another-Password-123"
SET_TENANT = "SELECT set_config('app.tenant_id', :tid, false)"


def token_for(tenant: SeededTenant, *, sub: Any = None, tid: Any = None) -> str:
    return create_access_token(
        {"sub": str(sub or tenant["user_id"]), "tid": str(tid or tenant["id"])}
    )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def use_tenant(conn: AsyncConnection, tenant_id: uuid.UUID) -> None:
    await conn.execute(text(SET_TENANT), {"tid": str(tenant_id)})


# --- database level -------------------------------------------------------


async def test_no_tenant_context_returns_no_rows(
    app_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    result = await app_conn.execute(text("SELECT count(*) FROM users"))
    assert result.scalar_one() == 0


async def test_cross_tenant_insert_fails_rls(
    app_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    await use_tenant(app_conn, two_tenants_seeded["tenant_a"]["id"])

    with pytest.raises(DBAPIError) as exc_info:
        await app_conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, password_hash, role) "
                "VALUES (:tid, 'hacker@tenantb.com', 'pass', 'agent')"
            ),
            {"tid": two_tenants_seeded["tenant_b"]["id"]},
        )

    assert sqlstate(exc_info.value) == "42501"
    assert "row-level security policy" in str(exc_info.value).lower()


async def test_cross_tenant_update_and_delete_affect_no_rows(
    app_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a, b = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    await use_tenant(app_conn, a["id"])

    updated = await app_conn.execute(
        text("UPDATE users SET role = 'admin' WHERE id = :bid"),
        {"bid": b["user_id"]},
    )
    deleted = await app_conn.execute(
        text("DELETE FROM users WHERE id = :bid"), {"bid": b["user_id"]}
    )
    assert updated.rowcount == 0
    assert deleted.rowcount == 0


async def test_unfiltered_select_by_id_under_other_tenant_returns_nothing(
    app_conn: AsyncConnection, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a, b = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    await use_tenant(app_conn, a["id"])

    # Deliberately no tenant_id filter: only RLS stands between A and B's row.
    result = await app_conn.execute(
        text("SELECT * FROM users WHERE id = :bid"), {"bid": b["user_id"]}
    )
    assert result.all() == []


async def test_cross_tenant_update_leaves_row_intact(
    owner_conn: AsyncConnection,
    app_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    a, b = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    await use_tenant(app_conn, a["id"])
    await app_conn.execute(
        text("UPDATE users SET role = 'admin' WHERE id = :bid"), {"bid": b["user_id"]}
    )
    await app_conn.commit()

    role = await owner_conn.execute(
        text("SELECT role FROM users WHERE id = :bid"), {"bid": b["user_id"]}
    )
    assert role.scalar_one() == "agent"


# --- API level ------------------------------------------------------------


async def test_get_users_lists_only_tenant_users(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    tenant_a = two_tenants_seeded["tenant_a"]

    response = await client.get("/users", headers=auth(token_for(tenant_a)))

    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["email"] == tenant_a["email"]
    assert users[0]["tenant_id"] == str(tenant_a["id"])


async def test_list_pagination_limits(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    headers = auth(token_for(two_tenants_seeded["tenant_a"]))

    assert (await client.get("/users?limit=1", headers=headers)).status_code == 200
    assert len((await client.get("/users?offset=1", headers=headers)).json()) == 0
    assert (await client.get("/users?limit=101", headers=headers)).status_code == 422
    assert (await client.get("/users?limit=0", headers=headers)).status_code == 422
    assert (await client.get("/users?offset=-1", headers=headers)).status_code == 422


async def test_get_own_user_returns_200(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a = two_tenants_seeded["tenant_a"]
    response = await client.get(f"/users/{a['user_id']}", headers=auth(token_for(a)))
    assert response.status_code == 200
    assert response.json()["id"] == str(a["user_id"])


async def test_get_other_tenant_user_returns_404(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a, b = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]

    response = await client.get(f"/users/{b['user_id']}", headers=auth(token_for(a)))

    assert response.status_code == 404


async def test_mismatched_tenant_and_user_token_returns_401(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a, b = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]

    # B's tenant id with A's user id as subject.
    response = await client.get("/users", headers=auth(token_for(a, tid=b["id"])))

    assert response.status_code == 401


async def test_deactivated_user_token_returns_401(
    client: AsyncClient,
    owner_conn: AsyncConnection,
    two_tenants_seeded: dict[str, SeededTenant],
) -> None:
    a = two_tenants_seeded["tenant_a"]
    await owner_conn.execute(
        text("UPDATE users SET is_active = false WHERE id = :uid"),
        {"uid": a["user_id"]},
    )
    await owner_conn.commit()

    response = await client.get("/users", headers=auth(token_for(a)))

    assert response.status_code == 401


async def test_agent_role_cannot_create_user_returns_403(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    b = two_tenants_seeded["tenant_b"]  # role: agent

    response = await client.post(
        "/users",
        json={
            "email": "new_agent@tenantb.com",
            "password": NEW_PASSWORD,
            "role": "agent",
        },
        headers=auth(token_for(b)),
    )

    assert response.status_code == 403


async def test_admin_creates_user_who_can_log_in(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a = two_tenants_seeded["tenant_a"]
    email = f"new@{a['slug']}.example.com"

    response = await client.post(
        "/users",
        json={"email": email, "password": NEW_PASSWORD, "role": "agent"},
        headers=auth(token_for(a)),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["tenant_id"] == str(a["id"])
    assert body["role"] == "agent"

    login = await client.post(
        "/auth/login",
        json={"tenant_slug": a["slug"], "email": email, "password": NEW_PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


async def test_duplicate_email_in_same_tenant_returns_409(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a = two_tenants_seeded["tenant_a"]

    response = await client.post(
        "/users",
        json={"email": a["email"].upper(), "password": NEW_PASSWORD},
        headers=auth(token_for(a)),
    )

    assert response.status_code == 409


async def test_same_email_in_other_tenant_returns_201(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a, b = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]

    response = await client.post(
        "/users",
        json={"email": b["email"], "password": NEW_PASSWORD},
        headers=auth(token_for(a)),
    )

    assert response.status_code == 201
    assert response.json()["tenant_id"] == str(a["id"])


async def test_missing_garbage_and_expired_tokens_return_401(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a = two_tenants_seeded["tenant_a"]
    expired = create_access_token(
        {"sub": str(a["user_id"]), "tid": str(a["id"])}, timedelta(seconds=-60)
    )

    assert (await client.get("/users")).status_code == 401
    assert (await client.get("/users", headers=auth("garbage"))).status_code == 401
    assert (await client.get("/users", headers=auth(expired))).status_code == 401
    assert (await client.post("/users", json={})).status_code == 401


async def test_login_invalid_credentials_returns_identical_response(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a = two_tenants_seeded["tenant_a"]

    wrong_pass = await client.post(
        "/auth/login",
        json={
            "tenant_slug": a["slug"],
            "email": a["email"],
            "password": "WrongPassword!",
        },
    )
    unknown_email = await client.post(
        "/auth/login",
        json={
            "tenant_slug": a["slug"],
            "email": "nonexistent@email.com",
            "password": SEED_PASSWORD,
        },
    )
    unknown_slug = await client.post(
        "/auth/login",
        json={
            "tenant_slug": "t-nonexistent-slug",
            "email": a["email"],
            "password": SEED_PASSWORD,
        },
    )

    assert wrong_pass.status_code == 401
    assert unknown_email.status_code == 401
    assert unknown_slug.status_code == 401
    assert wrong_pass.json() == unknown_email.json() == unknown_slug.json()


async def test_responses_never_contain_password_material(
    client: AsyncClient, two_tenants_seeded: dict[str, SeededTenant]
) -> None:
    a = two_tenants_seeded["tenant_a"]
    headers = auth(token_for(a))
    created = await client.post(
        "/users",
        json={"email": f"leak@{a['slug']}.example.com", "password": NEW_PASSWORD},
        headers=headers,
    )
    responses = [
        created,
        await client.get("/users", headers=headers),
        await client.get(f"/users/{a['user_id']}", headers=headers),
        await client.get("/auth/me", headers=headers),
    ]

    for response in responses:
        assert response.status_code in (200, 201)
        body = response.text
        assert "password_hash" not in body
        assert "password" not in body
        assert "argon2" not in body
        assert NEW_PASSWORD not in body


async def test_commit_failure_returns_500_not_2xx(
    two_tenants_seeded: dict[str, SeededTenant],
    owner_conn: AsyncConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves scope="function": the commit runs before the response is sent."""
    a = two_tenants_seeded["tenant_a"]
    email = f"doomed@{a['slug']}.example.com"

    async def failing_commit(self: AsyncSession) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/users",
            json={"email": email, "password": NEW_PASSWORD},
            headers=auth(token_for(a)),
        )

    assert response.status_code == 500
    stored = await owner_conn.execute(
        text("SELECT count(*) FROM users WHERE email = :email"), {"email": email}
    )
    assert stored.scalar_one() == 0
