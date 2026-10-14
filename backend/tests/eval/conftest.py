import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

MakeEvalTenant = Callable[..., Awaitable[uuid.UUID]]


@pytest.fixture
async def make(owner_conn: AsyncConnection) -> AsyncIterator[MakeEvalTenant]:
    """Tenants with a chosen slug, user emails and age, created as the owner and
    deleted by explicit id at teardown (never by pattern)."""
    created: list[uuid.UUID] = []

    async def _make(slug: str, emails: list[str], age_minutes: int = 60) -> uuid.UUID:
        tenant_id = (
            await owner_conn.execute(
                text(
                    "INSERT INTO tenants (slug, name, created_at) VALUES "
                    "(:s, :s, now() - make_interval(mins => :m)) RETURNING id"
                ),
                {"s": slug, "m": age_minutes},
            )
        ).scalar_one()
        created.append(tenant_id)
        for email in emails:
            await owner_conn.execute(
                text(
                    "INSERT INTO users (tenant_id, email, password_hash, role, "
                    "is_active) VALUES (:t, :e, 'x', 'admin', false)"
                ),
                {"t": tenant_id, "e": email},
            )
        await owner_conn.commit()
        return tenant_id

    yield _make
    for tenant_id in created:
        await owner_conn.execute(
            text("DELETE FROM tenants WHERE id = :i"), {"i": tenant_id}
        )
    await owner_conn.commit()


@pytest.fixture
def dead_pid() -> int:
    """A pid that belonged to a process which has already exited."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid
