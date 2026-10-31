"""Every auth rejection logs a fixed reason, never the token or its claims."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import create_access_token
from tests.conftest import MakeTenant, SeededTenant

MARKER = "MARKER-must-never-be-logged"
ENDPOINTS = ["/auth/me", "/documents"]


def _claims(t: SeededTenant, **extra: Any) -> dict[str, Any]:
    return {
        "sub": str(t["user_id"]),
        "tid": str(t["id"]),
        "typ": "access",
        "marker": MARKER,
        **extra,
    }


def _encode(payload: dict[str, Any], secret: str | None = None) -> str:
    return jwt.encode(
        payload,
        secret or settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _exp(delta: timedelta) -> datetime:
    return datetime.now(UTC) + delta


async def _reasons(
    client: AsyncClient, endpoint: str, token: str, caplog: pytest.LogCaptureFixture
) -> tuple[list[str], str]:
    caplog.clear()
    with caplog.at_level(logging.INFO):
        response = await client.get(
            endpoint, headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 401
    lines = [r.getMessage() for r in caplog.records]
    reasons = [m for m in lines if m.startswith("auth_rejected reason=")]
    return reasons, caplog.text


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("expired", "ExpiredSignatureError"),
        ("immature", "ImmatureSignatureError"),
        ("bad-signature", "InvalidSignatureError"),
        ("missing-tid", "MissingRequiredClaimError"),
        ("garbage", "DecodeError"),
        ("bad-claim-type", "invalid_claim"),
        ("user-not-found", "user_not_found"),
        ("other-tenant-user", "user_not_found"),
    ],
)
async def test_rejection_logs_reason_only(
    client: AsyncClient,
    make_tenant: MakeTenant,
    caplog: pytest.LogCaptureFixture,
    endpoint: str,
    case: str,
    expected: str,
) -> None:
    t = await make_tenant()
    other = await make_tenant()
    tokens = {
        "expired": _encode(_claims(t, exp=_exp(timedelta(minutes=-5)))),
        "immature": _encode(
            _claims(t, exp=_exp(timedelta(hours=1)), nbf=_exp(timedelta(minutes=30)))
        ),
        "bad-signature": _encode(
            _claims(t, exp=_exp(timedelta(hours=1))), secret="x" * 40
        ),
        "missing-tid": _encode(
            {
                "sub": str(t["user_id"]),
                "marker": MARKER,
                "exp": _exp(timedelta(hours=1)),
            }
        ),
        "garbage": f"not.a.jwt.{MARKER}",
        "bad-claim-type": _encode(_claims(t, tid=123, exp=_exp(timedelta(hours=1)))),
        "user-not-found": create_access_token(_claims(t, sub=str(uuid.uuid4()))),
        "other-tenant-user": create_access_token(_claims(t, sub=str(other["user_id"]))),
    }
    token = tokens[case]

    reasons, text = await _reasons(client, endpoint, token, caplog)

    assert reasons == [f"auth_rejected reason={expected}"]
    assert MARKER not in text
    assert token not in text
    assert t["email"] not in text
