"""Immutable citation snapshots linking outreach drafts to the company facts they used."""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "draft_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("draft_id", sa.String(36), nullable=False),
        sa.Column("fact_id", sa.String(36)),
        sa.Column("field", sa.String(80), nullable=False),
        sa.Column("value", sa.String(1000), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=False),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("citation_id", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["message_drafts.workspace_id", "message_drafts.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_draft_evidence_workspace_id", "draft_evidence", ["workspace_id"])
    op.create_index("ix_draft_evidence_draft", "draft_evidence", ["workspace_id", "draft_id"])
    op.execute("ALTER TABLE draft_evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE draft_evidence FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON draft_evidence USING (workspace_id = nullif("
        "current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif("
        "current_setting('app.workspace_id', true), ''))"
    )


def downgrade():
    op.drop_table("draft_evidence")
