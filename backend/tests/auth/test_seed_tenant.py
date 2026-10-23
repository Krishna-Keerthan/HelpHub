"""scripts/seed_tenant.py creates a tenant and admin while registration is off."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import SEED_PASSWORD, _delete_tenants

BACKEND = Path(__file__).resolve().parents[2]


def run_script(
    slug: str, email: str, password: str
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "SEED_ADMIN_PASSWORD": password,
        "ALLOW_PUBLIC_REGISTRATION": "false",
    }
    return subprocess.run(  # noqa: S603 - fixed argv, test-controlled values
        [
            sys.executable,
            "scripts/seed_tenant.py",
            "--name",
            "Seeded",
            "--slug",
            slug,
            "--email",
            email,
        ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


async def test_seed_creates_a_tenant_whose_admin_can_log_in(
    client: AsyncClient, owner_conn: AsyncConnection
) -> None:
    slug = f"t-{uuid.uuid4().hex[:12]}"
    email = f"admin@{slug}.example.com"
    try:
        result = run_script(slug, email, SEED_PASSWORD)
        assert result.returncode == 0, result.stderr
        assert SEED_PASSWORD not in result.stdout + result.stderr
        assert "token" not in result.stdout.lower()

        login = await client.post(
            "/auth/login",
            json={"tenant_slug": slug, "email": email, "password": SEED_PASSWORD},
        )
        assert login.status_code == 200
        me = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert me.json()["role"] == "admin"

        # The public route stays closed while the flag is off.
        closed = await client.post(
            "/auth/register",
            json={
                "tenant_name": "x",
                "tenant_slug": slug + "z",
                "email": email,
                "password": SEED_PASSWORD,
            },
        )
        assert closed.status_code == 403
    finally:
        rows = await owner_conn.execute(
            text("SELECT id FROM tenants WHERE slug = :s"), {"s": slug}
        )
        await owner_conn.rollback()
        await _delete_tenants([row[0] for row in rows])


async def test_seed_refuses_a_taken_slug_and_a_weak_password(
    make_tenant,  # type: ignore[no-untyped-def]
) -> None:
    tenant = await make_tenant()
    taken = run_script(tenant["slug"], "other@example.com", SEED_PASSWORD)
    assert taken.returncode == 1
    assert "already taken" in taken.stderr

    weak = run_script(f"t-{uuid.uuid4().hex[:12]}", "a@example.com", "short-pw")
    assert weak.returncode == 2
    assert "short-pw" not in weak.stderr
