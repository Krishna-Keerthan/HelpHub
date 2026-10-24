"""users: allow the read-only 'viewer' role

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-23 00:00:00.000000

The role check constraint gains 'viewer'. Downgrade fails while any viewer user
exists (the old constraint rejects the row); delete or change those users first.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# op.f: the full name, so the metadata naming convention is not applied twice.
CONSTRAINT = op.f("ck_users_role")


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(CONSTRAINT, "users", type_="check")
    op.create_check_constraint(
        CONSTRAINT, "users", "role IN ('admin', 'agent', 'viewer')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(CONSTRAINT, "users", type_="check")
    op.create_check_constraint(CONSTRAINT, "users", "role IN ('admin', 'agent')")
