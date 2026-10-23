"""refresh_tokens rows follow the same tenant isolation as every tenant table."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.conftest import SeededTenant, sqlstate

RLS_VIOLATION = "42501"
Tenants = dict[str, SeededTenant]
INSERT = (
    "INSERT INTO refresh_tokens (jti, tenant_id, user_id, family_id, expires_at) "
    "VALUES (:jti, :tid, :uid, :fid, :exp)"
)


def params(tenant: SeededTenant, jti: uuid.UUID | None = None) -> dict[str, object]:
    return {
        "jti": jti or uuid.uuid4(),
        "tid": tenant["id"],
        "uid": tenant["user_id"],
        "fid": uuid.uuid4(),
        "exp": datetime.now(UTC) + timedelta(days=1),
    }


async def use_tenant(conn: AsyncConnection, tenant_id: uuid.UUID) -> None:
    await conn.execute(
        text("SELECT set_config('app.tenant_id', :tid, false)"), {"tid": str(tenant_id)}
    )
    await conn.commit()


async def seed_as_owner(owner_conn: AsyncConnection, tenant: SeededTenant) -> uuid.UUID:
    jti = uuid.uuid4()
    await owner_conn.execute(text(INSERT), params(tenant, jti))
    await owner_conn.commit()
    return jti


async def test_other_tenant_cannot_read_update_or_delete_a_token(
    app_conn: AsyncConnection, owner_conn: AsyncConnection, two_tenants_seeded: Tenants
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    jti = await seed_as_owner(owner_conn, ta)
    await use_tenant(app_conn, tb["id"])

    seen = await app_conn.execute(text("SELECT count(*) FROM refresh_tokens"))
    assert seen.scalar_one() == 0
    updated = await app_conn.execute(
        text("UPDATE refresh_tokens SET revoked_at = now() WHERE jti = :j"), {"j": jti}
    )
    deleted = await app_conn.execute(
        text("DELETE FROM refresh_tokens WHERE jti = :j"), {"j": jti}
    )
    assert (updated.rowcount, deleted.rowcount) == (0, 0)
    await app_conn.commit()

    await owner_conn.rollback()
    row = await owner_conn.execute(
        text("SELECT revoked_at FROM refresh_tokens WHERE jti = :j"), {"j": jti}
    )
    assert row.one() == (None,)  # still there, untouched


async def test_insert_for_another_tenant_fails_rls(
    app_conn: AsyncConnection, two_tenants_seeded: Tenants
) -> None:
    ta, tb = two_tenants_seeded["tenant_a"], two_tenants_seeded["tenant_b"]
    await use_tenant(app_conn, ta["id"])

    with pytest.raises(DBAPIError) as exc_info:
        await app_conn.execute(text(INSERT), params(tb))
    assert sqlstate(exc_info.value) == RLS_VIOLATION


async def test_no_tenant_context_sees_nothing(
    app_conn: AsyncConnection, owner_conn: AsyncConnection, two_tenants_seeded: Tenants
) -> None:
    await seed_as_owner(owner_conn, two_tenants_seeded["tenant_a"])

    seen = await app_conn.execute(text("SELECT count(*) FROM refresh_tokens"))
    assert seen.scalar_one() == 0


async def test_own_tenant_sees_its_tokens(
    app_conn: AsyncConnection, owner_conn: AsyncConnection, two_tenants_seeded: Tenants
) -> None:
    ta = two_tenants_seeded["tenant_a"]
    await seed_as_owner(owner_conn, ta)
    await use_tenant(app_conn, ta["id"])

    seen = await app_conn.execute(text("SELECT count(*) FROM refresh_tokens"))
    assert seen.scalar_one() == 1
