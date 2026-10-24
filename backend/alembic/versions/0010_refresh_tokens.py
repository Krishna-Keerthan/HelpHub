"""refresh_tokens: single-use refresh tokens with rotation families, with RLS

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_MATCH = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "refresh_tokens",
        sa.Column("jti", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_refresh_tokens_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_refresh_tokens_tenant_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("jti", name="pk_refresh_tokens"),
    )
    op.create_index(
        "ix_refresh_tokens_tenant_family", "refresh_tokens", ["tenant_id", "family_id"]
    )
    op.create_index(
        "ix_refresh_tokens_tenant_expires",
        "refresh_tokens",
        ["tenant_id", "expires_at"],
    )
    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON refresh_tokens FOR ALL "
        f"USING ({TENANT_MATCH}) WITH CHECK ({TENANT_MATCH})"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY tenant_isolation ON refresh_tokens")
    op.execute("ALTER TABLE refresh_tokens DISABLE ROW LEVEL SECURITY")
    op.drop_table("refresh_tokens")
