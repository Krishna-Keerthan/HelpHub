import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

TENANT_TABLES_QUERY = """
    SELECT
        c.relname AS table_name,
        c.relrowsecurity AS has_rls,
        COUNT(p.policyname) AS policy_count
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a
      ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
    LEFT JOIN pg_policies p
      ON p.schemaname = n.nspname AND p.tablename = c.relname
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p')
    GROUP BY c.relname, c.relrowsecurity
"""


async def test_all_tenant_tables_have_rls_and_policies(
    owner_conn: AsyncConnection,
) -> None:
    """
    Finds all tables with a 'tenant_id' column and asserts:
    1. relrowsecurity = true
    2. At least one RLS policy exists
    """
    result = await owner_conn.execute(text(TENANT_TABLES_QUERY))
    tables = result.mappings().all()

    assert len(tables) > 0, "No tables with 'tenant_id' column found in public schema."

    for table in tables:
        assert table["has_rls"] is True, (
            f"Table '{table['table_name']}' has tenant_id but RLS is NOT enabled!"
        )
        assert table["policy_count"] > 0, (
            f"Table '{table['table_name']}' has RLS enabled but NO policies defined!"
        )


async def test_tenant_policies_filter_on_app_tenant_id(
    owner_conn: AsyncConnection,
) -> None:
    """A policy like USING (true) would pass the test above but isolate nothing."""
    result = await owner_conn.execute(
        text(
            """
            SELECT p.tablename, p.policyname, p.qual, p.with_check
            FROM pg_policies p
            WHERE p.schemaname = 'public'
              AND p.tablename IN (
                  SELECT c.relname
                  FROM pg_class c
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                  JOIN pg_attribute a ON a.attrelid = c.oid
                   AND a.attname = 'tenant_id' AND NOT a.attisdropped
                  WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
              )
            """
        )
    )
    policies = result.mappings().all()

    assert policies, "No policies found on tenant tables."
    for policy in policies:
        name = f"{policy['tablename']}.{policy['policyname']}"
        assert "app.tenant_id" in (policy["qual"] or ""), f"{name}: USING lacks it"
        assert "app.tenant_id" in (policy["with_check"] or ""), (
            f"{name}: WITH CHECK lacks it"
        )


@pytest.mark.parametrize("table", ["tenants", "users", "documents", "chunks"])
@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE"])
async def test_app_role_has_table_privileges(
    owner_conn: AsyncConnection, table: str, privilege: str
) -> None:
    result = await owner_conn.execute(
        text("SELECT has_table_privilege('helphub_app', :table, :privilege)"),
        {"table": f"public.{table}", "privilege": privilege},
    )
    assert result.scalar_one() is True, f"helphub_app lacks {privilege} on {table}"
