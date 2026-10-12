import uuid
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.core.security import DUMMY_HASH, create_access_token
from app.services import auth as auth_service
from tests.conftest import MakeTenant

PASSWORD = "correct-horse-battery"


@pytest.fixture
async def registered_ids(owner_conn: AsyncConnection) -> AsyncIterator[list[str]]:
    """Tenant ids created through /auth/register; deleted by id at teardown."""
    ids: list[str] = []
    yield ids
    for tenant_id in ids:
        await owner_conn.execute(
            text("DELETE FROM tenants WHERE id = :id"), {"id": uuid.UUID(tenant_id)}
        )
    await owner_conn.commit()


@pytest.fixture
def register(client: AsyncClient, registered_ids: list[str]) -> Callable[..., Any]:
    async def _register(
        slug: str | None = None, email: str = "Admin@Acme.example.com"
    ) -> Response:
        slug = slug or f"acme-{uuid.uuid4().hex[:10]}"
        resp = await client.post(
            "/auth/register",
            json={
                "tenant_name": "Acme",
                "tenant_slug": slug,
                "email": email,
                "password": PASSWORD,
            },
        )
        if resp.status_code == 201:
            registered_ids.append(resp.json()["user"]["tenant_id"])
        return resp

    return _register


def login_body(slug: str, email: str, password: str) -> dict[str, str]:
    return {"tenant_slug": slug, "email": email, "password": password}


async def test_register_login_me(client: AsyncClient, register: Callable[..., Any]):
    slug = f"acme-{uuid.uuid4().hex[:10]}"
    resp = await register(slug=slug)
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "admin@acme.example.com"
    assert body["user"]["role"] == "admin"
    assert body["token_type"] == "bearer"

    login = await client.post(
        "/auth/login", json=login_body(slug, "ADMIN@acme.example.com", PASSWORD)
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]
    assert me.json()["tenant_id"] == body["user"]["tenant_id"]

    # The token returned by register works as well.
    me2 = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me2.status_code == 200


async def test_register_duplicate_slug_409(register: Callable[..., Any]):
    slug = f"dup-{uuid.uuid4().hex[:10]}"
    assert (await register(slug=slug)).status_code == 201
    resp = await register(slug=slug, email="other@acme.example.com")
    assert resp.status_code == 409


async def test_register_disabled_403(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, register: Callable[..., Any]
):
    monkeypatch.setattr(settings, "allow_public_registration", False)
    resp = await register()
    assert resp.status_code == 403


async def test_login_failures_are_identical(
    client: AsyncClient, make_tenant: MakeTenant
):
    active = await make_tenant()
    inactive = await make_tenant(is_active=False)
    cases = {
        "wrong_password": login_body(
            active["slug"], active["email"], "wrong-password-1"
        ),
        "unknown_email": login_body(active["slug"], "nobody@x.example.com", PASSWORD),
        "unknown_tenant": login_body(
            f"nope-{uuid.uuid4().hex[:8]}", "a@x.example.com", PASSWORD
        ),
        "inactive_user": login_body(
            inactive["slug"], inactive["email"], inactive["password"]
        ),
    }
    responses = {
        name: await client.post("/auth/login", json=body)
        for name, body in cases.items()
    }
    reference = responses["wrong_password"]
    assert reference.status_code == 401
    for name, resp in responses.items():
        assert resp.status_code == reference.status_code, name
        assert resp.json() == reference.json(), name
        assert resp.headers.get("www-authenticate") == "Bearer", name


@pytest.mark.parametrize("case", ["unknown_tenant", "unknown_user", "inactive_user"])
async def test_login_failure_verifies_against_dummy_hash(
    case: str,
    client: AsyncClient,
    make_tenant: MakeTenant,
    monkeypatch: pytest.MonkeyPatch,
):
    seeded = await make_tenant(is_active=case != "inactive_user")
    body = {
        "unknown_tenant": login_body(
            "nope-" + uuid.uuid4().hex[:8], "a@x.example.com", PASSWORD
        ),
        "unknown_user": login_body(seeded["slug"], "nobody@x.example.com", PASSWORD),
        "inactive_user": login_body(
            seeded["slug"], seeded["email"], seeded["password"]
        ),
    }[case]

    calls: list[tuple[str, str]] = []
    real = auth_service.verify_password

    def spy(password: str, hashed: str) -> bool:
        calls.append((password, hashed))
        return real(password, hashed)

    monkeypatch.setattr(auth_service, "verify_password", spy)
    resp = await client.post("/auth/login", json=body)
    assert resp.status_code == 401
    assert calls == [(body["password"], DUMMY_HASH)]


async def test_responses_never_leak_secrets(
    client: AsyncClient, register: Callable[..., Any]
):
    slug = f"leak-{uuid.uuid4().hex[:10]}"
    reg = await register(slug=slug)
    login = await client.post(
        "/auth/login", json=login_body(slug, "admin@acme.example.com", PASSWORD)
    )
    token = login.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    for resp in (reg, login, me):
        assert "password_hash" not in resp.text
        assert PASSWORD not in resp.text
        assert "argon2" not in resp.text


async def test_me_without_token_401(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_me_garbage_token_401(client: AsyncClient):
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_me_expired_token_401(client: AsyncClient, make_tenant: MakeTenant):
    seeded = await make_tenant()
    token = create_access_token(
        {"sub": str(seeded["user_id"]), "tid": str(seeded["id"])},
        expires_delta=timedelta(seconds=-10),
    )
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"
