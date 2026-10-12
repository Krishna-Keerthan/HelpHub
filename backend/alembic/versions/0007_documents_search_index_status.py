"""documents.search_index_status and search_index_error

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "documents",
        sa.Column(
            "search_index_status",
            sa.String(length=16),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "documents", sa.Column("search_index_error", sa.Text(), nullable=True)
    )
    # The naming convention adds the ck_documents_ prefix.
    op.create_check_constraint(
        "search_index_status",
        "documents",
        "search_index_status IN ('PENDING', 'INDEXED', 'FAILED')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Pass the short name: the naming convention adds the ck_documents_ prefix.
    op.drop_constraint("search_index_status", "documents", type_="check")
    op.drop_column("documents", "search_index_error")
    op.drop_column("documents", "search_index_status")
