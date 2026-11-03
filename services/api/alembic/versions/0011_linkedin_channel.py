"""LinkedIn channel: synthetic simulator accounts and auditable connection/message actions."""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
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


def _base():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "linkedin_sim_accounts",
        *_base(),
        sa.Column("handle", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("headline", sa.String(240), nullable=False),
        sa.Column("behaviour", sa.String(40), nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.UniqueConstraint("workspace_id", "handle"),
        sa.UniqueConstraint("workspace_id", "contact_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_linkedin_sim_accounts_workspace_id", "linkedin_sim_accounts", ["workspace_id"]
    )
    _rls("linkedin_sim_accounts")
    op.create_table(
        "linkedin_actions",
        *_base(),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36)),
        sa.Column("draft_id", sa.String(36)),
        sa.Column("draft_revision", sa.Integer()),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("content", sa.String(3000), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["message_drafts.workspace_id", "message_drafts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.CheckConstraint("channel IN ('simulator', 'manual')", name="linkedin_action_channel"),
        sa.CheckConstraint(
            "simulated = (channel = 'simulator')", name="linkedin_action_simulated_flag"
        ),
    )
    op.create_index("ix_linkedin_actions_workspace_id", "linkedin_actions", ["workspace_id"])
    op.create_index(
        "ix_linkedin_actions_contact", "linkedin_actions", ["workspace_id", "contact_id", "action"]
    )
    _rls("linkedin_actions")


def downgrade():
    op.drop_table("linkedin_actions")
    op.drop_table("linkedin_sim_accounts")
