"""drop documents.search_index_status and search_index_error (search index removed)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Pass the short name: the naming convention adds the ck_documents_ prefix.
    op.drop_constraint("search_index_status", "documents", type_="check")
    op.drop_column("documents", "search_index_error")
    op.drop_column("documents", "search_index_status")


def downgrade() -> None:
    """Downgrade schema (restores the 0007 shape)."""
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
    op.create_check_constraint(
        "search_index_status",
        "documents",
        "search_index_status IN ('PENDING', 'INDEXED', 'FAILED')",
    )
