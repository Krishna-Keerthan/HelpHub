import pytest
import asyncpg.exceptions
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_no_tenant_context_returns_no_rows(app_conn, two_tenants_seeded):
    result = await app_conn.execute(text("SELECT count(*) FROM users"))
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_cross_tenant_insert_fails_rls(app_conn, two_tenants_seeded):
    tenant_a_id = two_tenants_seeded["tenant_a"]["id"]
    tenant_b_id = two_tenants_seeded["tenant_b"]["id"]

    # Set context session variable to Tenant A
    await app_conn.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, false)"),
        {"tid": str(tenant_a_id)},
    )

    # Attempt inserting row carrying Tenant B's tenant_id while in Tenant A context
    with pytest.raises(DBAPIError) as exc_info:
        await app_conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, hashed_password, role) "
                "VALUES (:tid, 'hacker@tenantb.com', 'pass', 'agent')"
            ),
            {"tid": tenant_b_id},
        )

    # 1. Assert underlying driver error is asyncpg's InsufficientPrivilegeError
    assert isinstance(
        exc_info.value.orig, asyncpg.exceptions.InsufficientPrivilegeError
    )

    # 2. Or check Postgres SQLSTATE code / message string
    assert "row-level security policy" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_users_lists_only_tenant_users(client, two_tenants_seeded):
    tenant_a = two_tenants_seeded["tenant_a"]
    token = create_access_token(
        {"sub": tenant_a["email"], "tid": str(tenant_a["id"]), "role": "admin"}
    )

    response = await client.get("/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["email"] == tenant_a["email"]


@pytest.mark.asyncio
async def test_get_other_tenant_user_returns_404(client, two_tenants_seeded):
    tenant_a = two_tenants_seeded["tenant_a"]
    tenant_b_user_id = two_tenants_seeded["tenant_b"]["user_id"]

    token = create_access_token(
        {"sub": tenant_a["email"], "tid": str(tenant_a["id"]), "role": "admin"}
    )

    response = await client.get(
        f"/users/{tenant_b_user_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mismatched_tenant_and_user_token_returns_401(client, two_tenants_seeded):
    tenant_a_email = two_tenants_seeded["tenant_a"]["email"]
    tenant_b_id = two_tenants_seeded["tenant_b"]["id"]

    # Token forged with Tenant B's ID but Tenant A's user email
    mismatched_token = create_access_token(
        {"sub": tenant_a_email, "tid": str(tenant_b_id), "role": "admin"}
    )

    response = await client.get(
        "/users", headers={"Authorization": f"Bearer {mismatched_token}"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_deactivated_user_token_returns_401(
    client, owner_conn, two_tenants_seeded
):
    tenant_a = two_tenants_seeded["tenant_a"]

    # Deactivate User A via owner connection
    await owner_conn.execute(
        text("UPDATE users SET is_active = false WHERE id = :uid"),
        {"uid": tenant_a["user_id"]},
    )
    await owner_conn.commit()

    token = create_access_token(
        {"sub": tenant_a["email"], "tid": str(tenant_a["id"]), "role": "admin"}
    )

    response = await client.get("/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_role_cannot_create_user_returns_403(client, two_tenants_seeded):
    tenant_b = two_tenants_seeded["tenant_b"]  # Role: agent

    token = create_access_token(
        {"sub": tenant_b["email"], "tid": str(tenant_b["id"]), "role": "agent"}
    )

    response = await client.post(
        "/users",
        json={
            "email": "new_agent@tenantb.com",
            "password": "Password123!",
            "role": "agent",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_login_invalid_credentials_returns_identical_response(
    client, two_tenants_seeded
):
    tenant_a = two_tenants_seeded["tenant_a"]

    # 1. Wrong Password
    res_wrong_pass = await client.post(
        "/auth/login",
        json={
            "tenant_slug": tenant_a["slug"],
            "email": tenant_a["email"],
            "password": "WrongPassword!",
        },
    )

    # 2. Unknown Email
    res_unknown_email = await client.post(
        "/auth/login",
        json={
            "tenant_slug": tenant_a["slug"],
            "email": "nonexistent@email.com",
            "password": "Password123!",
        },
    )

    # 3. Unknown Tenant Slug
    res_unknown_slug = await client.post(
        "/auth/login",
        json={
            "tenant_slug": "t-nonexistent-slug",
            "email": tenant_a["email"],
            "password": "Password123!",
        },
    )

    # Verify all responses return identical status codes and payloads
    assert res_wrong_pass.status_code == 401
    assert res_unknown_email.status_code == 401
    assert res_unknown_slug.status_code == 401

    assert res_wrong_pass.json() == res_unknown_email.json() == res_unknown_slug.json()
