import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypedDict

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import hash_password
from app.main import app

SEED_PASSWORD = "Password123!Password"


class SeededTenant(TypedDict):
    id: uuid.UUID
    slug: str
    user_id: uuid.UUID
    email: str
    role: str
    password: str


MakeTenant = Callable[..., Awaitable[SeededTenant]]


@pytest.fixture
async def owner_conn() -> AsyncIterator[AsyncConnection]:
    """Connection as the table owner (MIGRATION_DATABASE_URL); bypasses RLS."""
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            yield conn
    finally:
        await engine.dispose()


@pytest.fixture
async def app_conn() -> AsyncIterator[AsyncConnection]:
    """Connection as the runtime role (DATABASE_URL); subject to RLS."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            yield conn
            await conn.rollback()
            # Tests may set the tenant at session level; never leave it behind.
            await conn.execute(text("SELECT set_config('app.tenant_id', '', false)"))
            await conn.commit()
    finally:
        await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture(scope="session")
def seed_password_hash() -> str:
    return hash_password(SEED_PASSWORD)


@pytest.fixture
async def make_tenant(seed_password_hash: str) -> AsyncIterator[MakeTenant]:
    """Factory: a committed tenant with one user, created as the owner.

    Cleanup deletes exactly the tenants this factory created (users go with
    them via ON DELETE CASCADE), never by pattern.
    """
    created: list[uuid.UUID] = []
    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)

    async def _make(
        *, role: str = "admin", is_active: bool = True, slug: str | None = None
    ) -> SeededTenant:
        slug = slug or f"t-{uuid.uuid4().hex[:12]}"
        email = f"user@{slug}.example.com"
        async with engine.begin() as conn:
            tenant_id = (
                await conn.execute(
                    text(
                        "INSERT INTO tenants (slug, name) VALUES (:slug, :name) "
                        "RETURNING id"
                    ),
                    {"slug": slug, "name": f"Tenant {slug}"},
                )
            ).scalar_one()
            user_id = (
                await conn.execute(
                    text(
                        "INSERT INTO users "
                        "(tenant_id, email, password_hash, role, is_active) "
                        "VALUES (:tid, :email, :hash, :role, :active) RETURNING id"
                    ),
                    {
                        "tid": tenant_id,
                        "email": email,
                        "hash": seed_password_hash,
                        "role": role,
                        "active": is_active,
                    },
                )
            ).scalar_one()
        created.append(tenant_id)
        return {
            "id": tenant_id,
            "slug": slug,
            "user_id": user_id,
            "email": email,
            "role": role,
            "password": SEED_PASSWORD,
        }

    try:
        yield _make
    finally:
        try:
            async with engine.begin() as conn:
                for tenant_id in created:
                    await conn.execute(
                        text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id}
                    )
        finally:
            await engine.dispose()


@pytest.fixture
async def two_tenants_seeded(
    make_tenant: MakeTenant,
) -> dict[str, SeededTenant]:
    """Tenant A (admin user) and tenant B (agent user)."""
    return {
        "tenant_a": await make_tenant(role="admin"),
        "tenant_b": await make_tenant(role="agent"),
    }
