"""V3 M1: contact points with source per channel, channel route, channel policy, merges."""

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def _base():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _rls(table):
    op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} USING (workspace_id = nullif("
        "current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif("
        "current_setting('app.workspace_id', true), ''))"
    )


def upgrade():
    op.add_column(
        "contacts", sa.Column("channel_route", sa.String(20), nullable=False, server_default="none")
    )
    op.add_column(
        "contacts", sa.Column("route_reason", sa.String(300), nullable=False, server_default="")
    )
    op.add_column(
        "contacts", sa.Column("route_mode", sa.String(10), nullable=False, server_default="auto")
    )
    op.add_column("contacts", sa.Column("route_set_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "contact_channel_route", "contacts", "channel_route IN ('linkedin', 'letter', 'none')"
    )
    op.create_table(
        "contact_points",
        *_base(),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("workspace_id", "contact_id", "channel", "value"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "channel IN ('linkedin', 'postal', 'email', 'phone')", name="contact_point_channel"
        ),
    )
    _rls("contact_points")
    op.create_table(
        "channel_policies",
        *_base(),
        sa.Column("cold_email_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("legal_review_note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("changed_by", sa.String(36)),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "changed_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )
    _rls("channel_policies")
    op.create_table(
        "contact_merges",
        *_base(),
        sa.Column("kept_contact_id", sa.String(36), nullable=False),
        sa.Column("merged_contact_id", sa.String(36), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "kept_contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )
    _rls("contact_merges")


def downgrade():
    op.drop_table("contact_merges")
    op.drop_table("channel_policies")
    op.drop_table("contact_points")
    op.drop_constraint("contact_channel_route", "contacts", type_="check")
    for name in ("route_set_at", "route_mode", "route_reason", "channel_route"):
        op.drop_column("contacts", name)
