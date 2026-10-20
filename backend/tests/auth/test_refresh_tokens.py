"""Refresh tokens: rotation, reuse detection, logout, and token-type separation."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.core.security import create_refresh_token
from app.services import auth as auth_service
from tests.conftest import MakeTenant, SeededTenant, auth_headers


async def login(client: AsyncClient, tenant: SeededTenant) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        json={
            "tenant_slug": tenant["slug"],
            "email": tenant["email"],
            "password": tenant["password"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def refresh(client: AsyncClient, token: str) -> Any:
    return await client.post("/auth/refresh", json={"refresh_token": token})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def rows(owner_conn: AsyncConnection, tenant: SeededTenant) -> list[Any]:
    await owner_conn.rollback()
    result = await owner_conn.execute(
        text(
            "SELECT jti, family_id, used_at, revoked_at, expires_at FROM refresh_tokens "
            "WHERE tenant_id = :t ORDER BY created_at, jti"
        ),
        {"t": tenant["id"]},
    )
    return list(result.mappings())


def jti_of(token: str) -> uuid.UUID:
    return uuid.UUID(jwt.decode(token, options={"verify_signature": False})["jti"])


# --- issue and rotate --------------------------------------------------------


async def test_login_returns_a_working_pair_with_the_documented_claims(
    client: AsyncClient, make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    pair = await login(client, tenant)

    refresh_claims = jwt.decode(
        pair["refresh_token"], options={"verify_signature": False}
    )
    assert {"sub", "tid", "jti", "typ", "exp"} <= refresh_claims.keys()
    assert refresh_claims["typ"] == "refresh"
    assert refresh_claims["sub"] == str(tenant["user_id"])
    assert refresh_claims["tid"] == str(tenant["id"])
    access_claims = jwt.decode(
        pair["access_token"], options={"verify_signature": False}
    )
    assert access_claims["typ"] == "access"
    me = await client.get("/auth/me", headers=bearer(pair["access_token"]))
    assert me.status_code == 200
    (row,) = await rows(owner_conn, tenant)
    assert row["jti"] == jti_of(pair["refresh_token"])
    assert row["used_at"] is None and row["revoked_at"] is None


async def test_default_lifetimes_are_15_minutes_and_7_days(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    from app.core.config import Settings

    fresh = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url="postgresql+asyncpg://x:y@h/d",
        migration_database_url="postgresql+asyncpg://x:y@h/d",
        jwt_secret="k" * 40,
    )
    assert (fresh.access_token_minutes, fresh.refresh_token_days) == (15, 7)


async def test_lifetimes_follow_the_settings(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "access_token_minutes", 3)
    monkeypatch.setattr(settings, "refresh_token_days", 2)
    pair = await login(client, await make_tenant())
    now = datetime.now(UTC).timestamp()
    access = jwt.decode(pair["access_token"], options={"verify_signature": False})
    refresh_ = jwt.decode(pair["refresh_token"], options={"verify_signature": False})
    assert access["exp"] - now == pytest.approx(180, abs=30)
    assert refresh_["exp"] - now == pytest.approx(2 * 86400, abs=30)


async def test_refresh_rotates_and_marks_the_old_token_used(
    client: AsyncClient, make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    first = await login(client, tenant)

    response = await refresh(client, first["refresh_token"])

    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (
        await client.get("/auth/me", headers=bearer(second["access_token"]))
    ).status_code == 200
    old, new = await rows(owner_conn, tenant)
    assert old["jti"] == jti_of(first["refresh_token"]) and old["used_at"] is not None
    assert new["jti"] == jti_of(second["refresh_token"]) and new["used_at"] is None
    assert old["family_id"] == new["family_id"]
    # The chain keeps working.
    assert (await refresh(client, second["refresh_token"])).status_code == 200


async def test_reusing_a_used_token_revokes_the_whole_family(
    client: AsyncClient, make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    first = await login(client, tenant)
    second = (await refresh(client, first["refresh_token"])).json()

    replay = await refresh(client, first["refresh_token"])

    assert replay.status_code == 401
    assert replay.json() == {"detail": "Invalid refresh token"}
    # The legitimate newest token is now dead too.
    assert (await refresh(client, second["refresh_token"])).status_code == 401
    assert all(r["revoked_at"] is not None for r in await rows(owner_conn, tenant))


async def test_reuse_revokes_only_its_own_family(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    one, other = await login(client, tenant), await login(client, tenant)
    await refresh(client, one["refresh_token"])
    await refresh(client, one["refresh_token"])  # replay: family one dies

    assert (await refresh(client, other["refresh_token"])).status_code == 200


async def test_expired_refresh_token_is_rejected(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    token = create_refresh_token(
        tenant["user_id"],
        tenant["id"],
        uuid.uuid4(),
        datetime.now(UTC) - timedelta(seconds=5),
    )
    assert (await refresh(client, token)).status_code == 401


async def test_stored_expiry_is_enforced_even_if_the_jwt_exp_is_later(
    client: AsyncClient, make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    pair = await login(client, tenant)
    await owner_conn.execute(
        text(
            "UPDATE refresh_tokens SET expires_at = now() - interval '1 second' WHERE tenant_id = :t"
        ),
        {"t": tenant["id"]},
    )
    await owner_conn.commit()

    assert (await refresh(client, pair["refresh_token"])).status_code == 401


async def test_unknown_jti_is_rejected(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    token = create_refresh_token(
        tenant["user_id"],
        tenant["id"],
        uuid.uuid4(),
        datetime.now(UTC) + timedelta(days=1),
    )
    assert (await refresh(client, token)).status_code == 401


async def test_inactive_user_cannot_refresh_and_loses_the_family(
    client: AsyncClient, make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    pair = await login(client, tenant)
    await owner_conn.execute(
        text("UPDATE users SET is_active = false WHERE id = :u"),
        {"u": tenant["user_id"]},
    )
    await owner_conn.commit()

    assert (await refresh(client, pair["refresh_token"])).status_code == 401
    (row,) = await rows(owner_conn, tenant)
    assert row["revoked_at"] is not None and row["used_at"] is None


async def test_a_token_naming_another_tenants_user_is_rejected(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    """The tenant is read from the verified token; a mismatched row is not honoured."""
    a, b = await make_tenant(), await make_tenant()
    pair_a = await login(client, a)
    jti = jti_of(pair_a["refresh_token"])
    forged = create_refresh_token(
        b["user_id"], a["id"], jti, datetime.now(UTC) + timedelta(days=1)
    )
    assert (await refresh(client, forged)).status_code == 401
    assert (await refresh(client, pair_a["refresh_token"])).status_code == 200


async def test_expired_rows_are_deleted_on_login_and_on_refresh(
    client: AsyncClient, make_tenant: MakeTenant, owner_conn: AsyncConnection
) -> None:
    tenant = await make_tenant()
    old = [uuid.uuid4(), uuid.uuid4()]
    for jti in old:
        await owner_conn.execute(
            text(
                "INSERT INTO refresh_tokens (jti, tenant_id, user_id, family_id, expires_at) "
                "VALUES (:j, :t, :u, gen_random_uuid(), now() - interval '1 day')"
            ),
            {"j": jti, "t": tenant["id"], "u": tenant["user_id"]},
        )
    await owner_conn.commit()

    pair = await login(client, tenant)
    assert {r["jti"] for r in await rows(owner_conn, tenant)}.isdisjoint(old)

    await owner_conn.execute(
        text(
            "INSERT INTO refresh_tokens (jti, tenant_id, user_id, family_id, expires_at) "
            "VALUES (:j, :t, :u, gen_random_uuid(), now() - interval '1 day')"
        ),
        {"j": old[0], "t": tenant["id"], "u": tenant["user_id"]},
    )
    await owner_conn.commit()
    await refresh(client, pair["refresh_token"])
    assert old[0] not in {r["jti"] for r in await rows(owner_conn, tenant)}


# --- logout -----------------------------------------------------------------


async def test_logout_revokes_the_family(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    first = await login(client, tenant)
    second = (await refresh(client, first["refresh_token"])).json()

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": second["refresh_token"]},
        headers=bearer(second["access_token"]),
    )

    assert response.status_code == 204
    assert (await refresh(client, second["refresh_token"])).status_code == 401
    assert (await refresh(client, first["refresh_token"])).status_code == 401


async def test_logout_needs_an_access_token_and_the_callers_own_refresh_token(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    a, b = await make_tenant(), await make_tenant()
    pair_a, pair_b = await login(client, a), await login(client, b)
    body = {"refresh_token": pair_a["refresh_token"]}

    assert (await client.post("/auth/logout", json=body)).status_code == 401
    assert (
        await client.post(
            "/auth/logout", json=body, headers=bearer(pair_b["access_token"])
        )
    ).status_code == 401
    assert (
        await refresh(client, pair_a["refresh_token"])
    ).status_code == 200  # untouched


async def test_logout_does_not_touch_other_logins(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    one, other = await login(client, tenant), await login(client, tenant)
    await client.post(
        "/auth/logout",
        json={"refresh_token": one["refresh_token"]},
        headers=bearer(one["access_token"]),
    )
    assert (await refresh(client, other["refresh_token"])).status_code == 200


# --- token types ------------------------------------------------------------

AUTHENTICATED = [
    ("GET", "/auth/me"),
    ("GET", "/users"),
    ("GET", "/documents"),
    ("GET", "/conversations"),
    ("POST", "/search"),
    ("POST", "/chat/stream"),
    ("POST", "/auth/logout"),
]


@pytest.mark.parametrize(("method", "path"), AUTHENTICATED)
async def test_refresh_token_is_rejected_everywhere_else(
    client: AsyncClient, make_tenant: MakeTenant, method: str, path: str
) -> None:
    pair = await login(client, await make_tenant())
    body = {"refresh_token": pair["refresh_token"], "query": "x", "message": "x"}

    response = await client.request(
        method,
        path,
        json=body if method == "POST" else None,
        headers=bearer(pair["refresh_token"]),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_access_token_is_rejected_at_refresh(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    response = await refresh(client, auth_headers(tenant)["Authorization"].split()[1])
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid refresh token"}


@pytest.mark.parametrize(
    "token",
    ["", "garbage", "a.b.c"],
)
async def test_malformed_refresh_tokens_are_401_or_422_never_500(
    client: AsyncClient, token: str
) -> None:
    assert (await refresh(client, token)).status_code in {401, 422}


async def test_refresh_token_signed_with_another_key_is_rejected(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    forged = jwt.encode(
        {
            "sub": str(tenant["user_id"]),
            "tid": str(tenant["id"]),
            "jti": str(uuid.uuid4()),
            "typ": "refresh",
            "exp": datetime.now(UTC) + timedelta(days=1),
        },
        "x" * 40,
        algorithm=settings.jwt_algorithm,
    )
    assert (await refresh(client, forged)).status_code == 401


async def test_refresh_is_verified_before_any_database_access(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await make_tenant()

    def no_database(*args: object, **kwargs: object) -> None:
        raise AssertionError("database touched before the token was verified")

    monkeypatch.setattr(auth_service, "tenant_transaction", no_database)
    access = auth_headers(tenant)["Authorization"].split()[1]
    for bad in ("garbage", access):
        assert (await refresh(client, bad)).status_code == 401


async def test_no_token_text_in_logs(
    client: AsyncClient,
    make_tenant: MakeTenant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant = await make_tenant()
    first = await login(client, tenant)
    with caplog.at_level("DEBUG"):
        await refresh(client, first["refresh_token"])
        await refresh(client, first["refresh_token"])  # reuse: logged at WARNING
    assert "refresh token reuse" in caplog.text
    assert first["refresh_token"] not in caplog.text
    assert first["access_token"] not in caplog.text
