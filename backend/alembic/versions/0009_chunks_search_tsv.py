"""chunks.search_tsv: generated tsvector with a GIN index (Postgres full-text search)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The text-search config is part of the expression: queries must use the
    # same one (TSCONFIG in app/db/repositories/chunks.py).
    op.add_column(
        "chunks",
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_chunks_search_tsv", "chunks", ["search_tsv"], postgresql_using="gin"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chunks_search_tsv", table_name="chunks")
    op.drop_column("chunks", "search_tsv")
