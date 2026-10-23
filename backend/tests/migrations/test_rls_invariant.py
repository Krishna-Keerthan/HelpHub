"""Every application table in public has RLS enabled and at least one policy.

Supabase enables RLS on each new table (event trigger ensure_rls); a table with
RLS on and no policy is closed to helphub_app, and one with RLS off differs from
Supabase. Requiring both keeps local, CI and Supabase identical.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

INVARIANT_SQL = text(
    """
    SELECT c.relname, c.relrowsecurity,
           (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
      AND NOT c.relispartition
      AND c.relname <> 'alembic_version'
    ORDER BY c.relname
    """
)


async def test_every_public_table_has_rls_and_a_policy(
    owner_conn: AsyncConnection,
) -> None:
    rows = (await owner_conn.execute(INVARIANT_SQL)).all()
    assert rows, "no application tables found"
    bad = [r.relname for r in rows if not r.relrowsecurity or r.policies < 1]
    assert bad == [], f"tables without RLS or without a policy: {bad}"
