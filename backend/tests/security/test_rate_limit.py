"""Login, search and chat are rate limited; 429 comes before any costly work."""

import pytest
from httpx import AsyncClient

from app.api.deps import get_embedding_provider
from app.core.config import settings
from app.main import app
from tests.conftest import MakeTenant, SeededTenant, auth_headers
from tests.helpers.fakes import FakeLLMProvider


@pytest.fixture(autouse=True)
def small_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_login_per_account", 3)
    monkeypatch.setattr(settings, "rate_limit_login_global", 5)
    monkeypatch.setattr(settings, "rate_limit_search_per_user", 2)
    monkeypatch.setattr(settings, "rate_limit_chat_per_user", 2)


def login_body(tenant: SeededTenant, password: str | None = None) -> dict[str, str]:
    return {
        "tenant_slug": tenant["slug"],
        "email": tenant["email"],
        "password": password or tenant["password"],
    }


async def test_login_blocks_the_account_after_the_limit_even_with_the_right_password(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    wrong = login_body(tenant, "Wrong-Password-123456")
    assert [
        (await client.post("/auth/login", json=wrong)).status_code for _ in range(3)
    ] == [401] * 3

    blocked = await client.post("/auth/login", json=login_body(tenant))
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json() == {
        "detail": "Too many requests"
    }  # no oracle about the password


async def test_login_limit_is_per_account_and_case_insensitive_on_the_slug(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    first, second = await make_tenant(), await make_tenant()
    for _ in range(3):
        await client.post(
            "/auth/login", json=login_body(first, "Wrong-Password-123456")
        )
    upper = {**login_body(first), "tenant_slug": first["slug"].upper()}
    assert (await client.post("/auth/login", json=upper)).status_code == 429
    assert (
        await client.post("/auth/login", json=login_body(second))
    ).status_code == 200


async def test_global_login_cap_applies_across_accounts(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenants = [await make_tenant() for _ in range(6)]
    codes = [
        (await client.post("/auth/login", json=login_body(t))).status_code
        for t in tenants
    ]
    assert codes == [200] * 5 + [429]


async def test_search_is_limited_per_user_and_blocked_before_embedding(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    one, other = await make_tenant(), await make_tenant()
    embedded: list[str] = []

    class CountingEmbedder:
        dim = 384
        model_name = "test"

        async def embed_query(self, text: str) -> list[float]:
            embedded.append(text)
            return [0.0] * 384

    app.dependency_overrides[get_embedding_provider] = CountingEmbedder
    body = {"query": "reset password"}
    codes = [
        (await client.post("/search", json=body, headers=auth_headers(one))).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]
    assert len(embedded) == 2  # the blocked request never embedded
    assert (
        await client.post("/search", json=body, headers=auth_headers(other))
    ).status_code == 200


async def test_chat_is_limited_per_user_and_blocked_before_any_work(
    client: AsyncClient, make_tenant: MakeTenant, fake_llm: FakeLLMProvider
) -> None:
    tenant = await make_tenant()
    codes = []
    for _ in range(3):
        response = await client.post(
            "/chat/stream",
            json={"message": "hello there"},
            headers=auth_headers(tenant),
        )
        codes.append(response.status_code)
    assert codes == [200, 200, 429]
    assert fake_llm.calls == 0  # nothing retrieved, so the refusal path ran twice


async def test_blocked_chat_stores_no_message(
    client: AsyncClient, make_tenant: MakeTenant
) -> None:
    tenant = await make_tenant()
    for _ in range(2):
        await client.post(
            "/chat/stream", json={"message": "one"}, headers=auth_headers(tenant)
        )
    before = await client.get("/conversations", headers=auth_headers(tenant))
    blocked = await client.post(
        "/chat/stream", json={"message": "two"}, headers=auth_headers(tenant)
    )
    after = await client.get("/conversations", headers=auth_headers(tenant))
    assert blocked.status_code == 429
    assert after.json() == before.json()


async def test_limits_can_be_switched_off(
    client: AsyncClient, make_tenant: MakeTenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    tenant = await make_tenant()
    codes = {
        (await client.post("/auth/login", json=login_body(tenant))).status_code
        for _ in range(8)
    }
    assert codes == {200}
