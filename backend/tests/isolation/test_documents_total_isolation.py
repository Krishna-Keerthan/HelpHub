import pytest

from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_total_count_never_counts_another_tenant(
    client, two_tenants_seeded, make_document
):
    ta = two_tenants_seeded["tenant_a"]
    tb = two_tenants_seeded["tenant_b"]
    await make_document(ta, raw_text="a only")
    for i in range(3):
        await make_document(tb, raw_text=f"b {i}")
    for tenant, expected in ((ta, 1), (tb, 3)):
        response = await client.get("/documents", headers=auth_headers(tenant))
        assert len(response.json()) == expected
        assert response.headers["X-Total-Count"] == str(expected)
