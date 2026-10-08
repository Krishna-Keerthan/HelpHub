"""users unique per tenant

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f("uq_users_email"), "users", type_="unique")
    op.create_unique_constraint(
        op.f("uq_users_tenant_id_email"), "users", ["tenant_id", "email"]
    )
    # Target for composite FKs (tenant_id, user_id) -> users(tenant_id, id).
    op.create_unique_constraint(
        op.f("uq_users_tenant_id_id"), "users", ["tenant_id", "id"]
    )


def downgrade() -> None:
    """Downgrade schema.

    Restoring the global unique fails with a unique violation if the same
    email exists in more than one tenant; deduplicate before downgrading.
    """
    op.drop_constraint(op.f("uq_users_tenant_id_id"), "users", type_="unique")
    op.drop_constraint(op.f("uq_users_tenant_id_email"), "users", type_="unique")
    op.create_unique_constraint(op.f("uq_users_email"), "users", ["email"])
