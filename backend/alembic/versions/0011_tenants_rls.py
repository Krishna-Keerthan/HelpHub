"""tenants: enable row level security with explicit policies for helphub_app

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-20 00:00:00.000000

Every table in public must have RLS enabled and at least one policy (checked by
tests/migrations/test_rls_invariant.py). Supabase's ensure_rls event trigger
turns RLS on for every new table, so without policies a table is closed to the
runtime role (this broke the tenants insert there); enabling it here and naming
the policies makes local, CI and Supabase behave the same.

tenants has no tenant_id: the app finds a tenant by slug before it knows the
tenant (login, registration), so the policies are not tenant-scoped. They grant
exactly the commands the app runs: SELECT (lookup by slug, and the RETURNING of
the insert) and INSERT (registration). No UPDATE or DELETE policy: the app never
runs them, so RLS now denies them.

No FORCE: the owner (migrations, test cleanup) still bypasses RLS. See AR-21 in
docs/review/accepted-risks.md.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenants_app_select ON tenants FOR SELECT TO helphub_app USING (true)"
    )
    op.execute(
        "CREATE POLICY tenants_app_insert ON tenants FOR INSERT TO helphub_app "
        "WITH CHECK (true)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY tenants_app_insert ON tenants")
    op.execute("DROP POLICY tenants_app_select ON tenants")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")
