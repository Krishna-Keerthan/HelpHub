"""The ``eval-`` tenant slug namespace is reserved for the evaluation harness."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.schemas.auth import RegisterRequest
from app.services import auth as auth_service

# gate-allow: secret fake value used only by this test
PASSWORD = "correct-horse-battery"


def _body(slug: str) -> dict[str, str]:
    return {
        "tenant_name": "Eval Corp",
        "tenant_slug": slug,
        "email": "admin@eval-corp.example.com",
        "password": PASSWORD,
    }


async def _tenant_count(owner_conn: AsyncConnection, slug: str) -> int:
    result = await owner_conn.execute(
        text("SELECT count(*) FROM tenants WHERE slug = :s"), {"s": slug}
    )
    return int(result.scalar_one())


@pytest.mark.usefixtures("registration_open")
async def test_api_rejects_eval_slugs_generically(
    client: AsyncClient, owner_conn: AsyncConnection
) -> None:
    resp = await client.post("/auth/register", json=_body("eval-corp"))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "slug not available"
    assert await _tenant_count(owner_conn, "eval-corp") == 0
    # Same answer for another reserved-looking slug: no hint about the list.
    other = await client.post("/auth/register", json=_body("eval-0123456789ab"))
    assert other.status_code == 422 and other.json() == resp.json()


@pytest.mark.usefixtures("registration_open")
async def test_non_eval_slug_is_still_accepted(
    client: AsyncClient, owner_conn: AsyncConnection
) -> None:
    slug = f"acme-{uuid.uuid4().hex[:10]}"
    resp = await client.post("/auth/register", json=_body(slug))
    try:
        assert resp.status_code == 201
    finally:
        await owner_conn.execute(
            text("DELETE FROM tenants WHERE slug = :s"), {"s": slug}
        )
        await owner_conn.commit()


@pytest.mark.usefixtures("registration_open")
async def test_service_refuses_eval_slug_unless_reserved_ok(
    owner_conn: AsyncConnection,
) -> None:
    slug = f"eval-{uuid.uuid4().hex[:12]}"
    data = RegisterRequest.model_validate(_body(slug))
    with pytest.raises(auth_service.ReservedSlug):
        await auth_service.register_tenant(data)
    assert await _tenant_count(owner_conn, slug) == 0
    user, _ = await auth_service.register_tenant(data, reserved_ok=True)
    try:
        assert await _tenant_count(owner_conn, slug) == 1
    finally:
        await owner_conn.execute(
            text("DELETE FROM tenants WHERE id = :i"), {"i": user.tenant_id}
        )
        await owner_conn.commit()


def test_reserved_ok_is_not_an_api_field() -> None:
    assert "reserved_ok" not in RegisterRequest.model_fields
