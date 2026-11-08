"""V3 M5: per-member pace limits and territory."""

import sqlalchemy as sa

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "member_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("daily_invite_limit", sa.Integer(), nullable=False),
        sa.Column("weekly_invite_limit", sa.Integer(), nullable=False),
        sa.Column("territory", sa.JSON(), nullable=False),
        sa.Column("receives_leads", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "user_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("daily_invite_limit BETWEEN 1 AND 30", name="member_daily_limit"),
        sa.CheckConstraint("weekly_invite_limit BETWEEN 1 AND 150", name="member_weekly_limit"),
    )
    op.create_index("ix_member_settings_workspace_id", "member_settings", ["workspace_id"])
    op.execute("ALTER TABLE member_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE member_settings FORCE ROW LEVEL SECURITY")
    # Merge records keep their history when the acting member leaves the team.
    op.alter_column("contact_merges", "actor_id", nullable=True)
    op.execute(
        "CREATE POLICY tenant_isolation ON member_settings USING (workspace_id = nullif("
        "current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif("
        "current_setting('app.workspace_id', true), ''))"
    )


def downgrade():
    op.drop_table("member_settings")
