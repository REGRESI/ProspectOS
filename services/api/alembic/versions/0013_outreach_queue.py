"""Daily LinkedIn queue ("Heute"), additive."""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outreach_queue_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("company_id", sa.String(36)),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(300), nullable=False),
        sa.Column("message", sa.String(1500), nullable=False),
        sa.Column("followup", sa.String(1500), nullable=False),
        sa.Column("followup_days", sa.Integer(), nullable=False),
        sa.Column("approved_by", sa.String(36)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("elapsed_ms", sa.Integer()),
        sa.Column("action_id", sa.String(36)),
        sa.UniqueConstraint("workspace_id", "day", "contact_id", "kind"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "company_id"], ["companies.workspace_id", "companies.id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "approved_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.CheckConstraint(
            "kind IN ('connect', 'message', 'followup')", name="outreach_queue_kind"
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'approved', 'sent', 'skipped')", name="outreach_queue_state"
        ),
    )
    op.create_index(
        "ix_outreach_queue_items_workspace_day", "outreach_queue_items", ["workspace_id", "day"]
    )
    op.execute("ALTER TABLE outreach_queue_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE outreach_queue_items FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON outreach_queue_items USING (workspace_id = nullif("
        "current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif("
        "current_setting('app.workspace_id', true), ''))"
    )


def downgrade():
    op.drop_table("outreach_queue_items")
