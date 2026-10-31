"""chunks tenant_id index

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-10 00:00:00.000000

Re-adds the tenant_id btree dropped in 0004: small-tenant search becomes an
exact index lookup, the exact fallback is bounded by the tenant's size, and
tenant delete cascades stop scanning chunks. See AR-15 in docs/review/accepted-risks.md.
Plain CREATE INDEX: on a populated production table use
CREATE INDEX CONCURRENTLY (outside a transaction) instead.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chunks_tenant_id", table_name="chunks")
