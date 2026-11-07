"""Verified LinkedIn profiles, content strategy, learning writing profile, per-user ownership.

Additive.

- contacts: LinkedIn check status with a reason in ProspectOS' own words (Brave titles
  and snippets are never stored), owner (the member who sends).
- companies: when the role search (Facility/Office/Praxis manager) last ran.
- social_posts: goal, audience, approach (A/B/C), pillar, campaign, planned day.
- content_campaigns, post_metrics (self-reported numbers 48 h after posting).
- draft_edits (original vs. user version), voice_feedback ("klingt nach mir"),
  style_inspirations (posts by others as style reference, never copied).
- connections: one LinkedIn connection per user instead of per workspace.
- workspace_invites: the owner role may be invited (by an owner only, checked in the API).
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

STATUS = "('unchecked', 'verified', 'confirmed', 'unsure', 'not_found')"
NEW_TABLES = (
    "content_campaigns",
    "post_metrics",
    "draft_edits",
    "voice_feedback",
    "style_inspirations",
)


def _tenant(name: str, *columns, constraints=()):
    op.create_table(
        name,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *columns,
        sa.UniqueConstraint("workspace_id", "id"),
        *constraints,
    )


def _member_fk(column: str):
    return sa.ForeignKeyConstraint(
        ["workspace_id", column], ["memberships.workspace_id", "memberships.user_id"]
    )


def upgrade():
    op.add_column(
        "contacts",
        sa.Column("linkedin_status", sa.String(20), nullable=False, server_default="unchecked"),
    )
    op.add_column(
        "contacts", sa.Column("linkedin_reason", sa.String(300), nullable=False, server_default="")
    )
    op.add_column("contacts", sa.Column("linkedin_checked_at", sa.DateTime(timezone=True)))
    op.add_column("contacts", sa.Column("owner_id", sa.String(36)))
    op.create_check_constraint(
        "contact_linkedin_status", "contacts", f"linkedin_status IN {STATUS}"
    )
    # Removing a member keeps their contacts and clears only the owner (PostgreSQL 15+).
    op.execute(
        "ALTER TABLE contacts ADD CONSTRAINT contact_owner_member FOREIGN KEY "
        "(workspace_id, owner_id) REFERENCES memberships (workspace_id, user_id) "
        "ON DELETE SET NULL (owner_id)"
    )
    op.execute(
        "UPDATE contacts SET linkedin_status = 'confirmed', "
        "linkedin_reason = 'Von dir bestätigt' WHERE coalesce(linkedin_url, '') <> ''"
    )
    op.add_column("companies", sa.Column("role_search_at", sa.DateTime(timezone=True)))

    _tenant(
        "content_campaigns",
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("goal", sa.String(20), nullable=False),
        sa.Column("audience", sa.String(30), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        constraints=(_member_fk("created_by"), sa.CheckConstraint("end_date >= start_date")),
    )
    for column in (
        sa.Column("goal", sa.String(20)),
        sa.Column("audience", sa.String(30)),
        sa.Column("approach", sa.String(1)),
        sa.Column("pillar", sa.String(120)),
        sa.Column("topic", sa.String(300)),
        sa.Column("campaign_id", sa.String(36)),
        sa.Column("planned_for", sa.Date()),
    ):
        op.add_column("social_posts", column)
    op.create_foreign_key(
        "post_campaign_tenant",
        "social_posts",
        "content_campaigns",
        ["workspace_id", "campaign_id"],
        ["workspace_id", "id"],
    )
    _tenant(
        "post_metrics",
        sa.Column("post_id", sa.String(36), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Integer(), nullable=False),
        sa.Column("profile_visits", sa.Integer(), nullable=False),
        sa.Column("inquiries", sa.Integer(), nullable=False),
        sa.Column("recorded_by", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        constraints=(
            sa.UniqueConstraint("workspace_id", "post_id"),
            sa.ForeignKeyConstraint(
                ["workspace_id", "post_id"], ["social_posts.workspace_id", "social_posts.id"]
            ),
            _member_fk("recorded_by"),
            sa.CheckConstraint(
                "impressions >= 0 AND comments >= 0 AND profile_visits >= 0 AND inquiries >= 0"
            ),
        ),
    )
    _tenant(
        "draft_edits",
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("ref_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("original", sa.String(3000), nullable=False),
        sa.Column("edited", sa.String(3000), nullable=False),
        constraints=(_member_fk("user_id"), sa.CheckConstraint("kind IN ('post', 'outreach')")),
    )
    _tenant(
        "voice_feedback",
        sa.Column("post_id", sa.String(36)),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("verdict", sa.String(3), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("text", sa.String(3000), nullable=False),
        constraints=(
            _member_fk("user_id"),
            sa.ForeignKeyConstraint(
                ["workspace_id", "post_id"], ["social_posts.workspace_id", "social_posts.id"]
            ),
            sa.CheckConstraint("verdict IN ('yes', 'no')"),
        ),
    )
    _tenant(
        "style_inspirations",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("author", sa.String(120), nullable=False, server_default=""),
        sa.Column("text", sa.String(3000), nullable=False),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        constraints=(_member_fk("user_id"),),
    )
    for name in NEW_TABLES:
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (workspace_id = nullif("
            "current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif("
            "current_setting('app.workspace_id', true), ''))"
        )

    # One LinkedIn connection per user. Existing rows belong to the workspace owner.
    op.add_column("connections", sa.Column("user_id", sa.String(36)))
    op.execute(
        "UPDATE connections c SET user_id = (SELECT m.user_id FROM memberships m "
        "WHERE m.workspace_id = c.workspace_id AND m.role = 'owner' ORDER BY m.user_id LIMIT 1)"
    )
    op.execute("DELETE FROM connections WHERE user_id IS NULL")
    op.alter_column("connections", "user_id", nullable=False)
    op.execute(
        "ALTER TABLE connections DROP CONSTRAINT IF EXISTS connections_workspace_id_provider_key"
    )
    op.create_unique_constraint(
        "connection_per_user", "connections", ["workspace_id", "provider", "user_id"]
    )
    op.create_foreign_key(
        "connection_member",
        "connections",
        "memberships",
        ["workspace_id", "user_id"],
        ["workspace_id", "user_id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("invite_role", "workspace_invites")
    op.create_check_constraint(
        "invite_role",
        "workspace_invites",
        "role IN ('owner','admin','editor','approver','analyst')",
    )


def downgrade():
    op.execute("DELETE FROM workspace_invites WHERE role = 'owner'")
    op.drop_constraint("invite_role", "workspace_invites")
    op.create_check_constraint(
        "invite_role", "workspace_invites", "role IN ('admin','editor','approver','analyst')"
    )
    op.drop_constraint("connection_member", "connections")
    op.drop_constraint("connection_per_user", "connections")
    op.execute(
        "DELETE FROM connections a USING connections b WHERE a.workspace_id = b.workspace_id "
        "AND a.provider = b.provider AND a.id > b.id"
    )
    op.create_unique_constraint(
        "connections_workspace_id_provider_key", "connections", ["workspace_id", "provider"]
    )
    op.drop_column("connections", "user_id")
    for name in ("style_inspirations", "voice_feedback", "draft_edits", "post_metrics"):
        op.drop_table(name)
    op.drop_constraint("post_campaign_tenant", "social_posts")
    for column in ("planned_for", "campaign_id", "topic", "pillar", "approach", "audience", "goal"):
        op.drop_column("social_posts", column)
    op.drop_table("content_campaigns")
    op.drop_column("companies", "role_search_at")
    op.drop_constraint("contact_owner_member", "contacts")
    op.drop_constraint("contact_linkedin_status", "contacts")
    for column in ("owner_id", "linkedin_checked_at", "linkedin_reason", "linkedin_status"):
        op.drop_column("contacts", column)
