"""Encrypted per-workspace integration credentials (additive)."""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _rls(table):
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} USING (workspace_id = nullif("
        "current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif("
        "current_setting('app.workspace_id', true), ''))"
    )


def upgrade():
    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("ciphertext", sa.String(8000), nullable=False),
        sa.Column("masked", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("last_error", sa.String(200), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "provider"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "updated_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.CheckConstraint(
            "status IN ('untested', 'connected', 'error')", name="integration_credential_status"
        ),
    )
    op.create_index(
        "ix_integration_credentials_workspace_id", "integration_credentials", ["workspace_id"]
    )
    _rls("integration_credentials")


def downgrade():
    op.drop_table("integration_credentials")
