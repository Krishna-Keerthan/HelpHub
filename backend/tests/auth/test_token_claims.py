"""Malformed or mismatched token claims are always a generic 401, never a 500."""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from tests.conftest import SeededTenant

Tenants = dict[str, SeededTenant]
ClaimsFor = Callable[[SeededTenant, SeededTenant], dict[str, Any]]

# One endpoint per auth dependency: CurrentUser (via TenantSession) and
# CurrentPrincipal.
ENDPOINTS = ["/auth/me", "/documents"]
GENERIC_401 = {"detail": "Not authenticated"}


def _ids(a: SeededTenant) -> tuple[str, str]:
    return str(a["user_id"]), str(a["id"])


BAD_CLAIMS: dict[str, ClaimsFor] = {
    "missing-sub": lambda a, b: {"tid": _ids(a)[1]},
    "missing-tid": lambda a, b: {"sub": _ids(a)[0]},
    "null-sub": lambda a, b: {"sub": None, "tid": _ids(a)[1]},
    "null-tid": lambda a, b: {"sub": _ids(a)[0], "tid": None},
    "non-uuid-sub": lambda a, b: {"sub": "abc", "tid": _ids(a)[1]},
    "non-uuid-tid": lambda a, b: {"sub": _ids(a)[0], "tid": "abc"},
    "empty-sub": lambda a, b: {"sub": "", "tid": _ids(a)[1]},
    "empty-tid": lambda a, b: {"sub": _ids(a)[0], "tid": ""},
    "int-sub": lambda a, b: {"sub": 123, "tid": _ids(a)[1]},
    "int-tid": lambda a, b: {"sub": _ids(a)[0], "tid": 123},
    "list-sub": lambda a, b: {"sub": [_ids(a)[0]], "tid": _ids(a)[1]},
    "list-tid": lambda a, b: {"sub": _ids(a)[0], "tid": [_ids(a)[1]]},
    "dict-tid": lambda a, b: {"sub": _ids(a)[0], "tid": {"id": _ids(a)[1]}},
    "bool-tid": lambda a, b: {"sub": _ids(a)[0], "tid": True},
    "urn-sub": lambda a, b: {"sub": f"urn:uuid:{_ids(a)[0]}", "tid": _ids(a)[1]},
    "braced-tid": lambda a, b: {"sub": _ids(a)[0], "tid": "{" + _ids(a)[1] + "}"},
    "uppercase-tid": lambda a, b: {"sub": _ids(a)[0], "tid": _ids(a)[1].upper()},
    "unknown-tenant": lambda a, b: {"sub": _ids(a)[0], "tid": str(uuid.uuid4())},
    "user-of-other-tenant": lambda a, b: {"sub": _ids(b)[0], "tid": _ids(a)[1]},
}


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("case", list(BAD_CLAIMS))
async def test_bad_claims_are_generic_401(
    client: AsyncClient, two_tenants_seeded: Tenants, endpoint: str, case: str
) -> None:
    a, b = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    token = create_access_token(BAD_CLAIMS[case](a, b))

    response = await client.get(endpoint, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401, response.text
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == GENERIC_401
