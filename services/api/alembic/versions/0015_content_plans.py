"""LinkedIn content strategy plans (additive)."""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("goal", sa.String(500), nullable=False),
        sa.Column("audience", sa.String(500), nullable=False),
        sa.Column("pillars", sa.JSON(), nullable=False),
        sa.Column("cadence", sa.Integer(), nullable=False),
        sa.Column("weeks", sa.Integer(), nullable=False),
        sa.Column("voice_profile_id", sa.String(36)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("storyline", sa.String(2000), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("job_id", sa.String(36)),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "voice_profile_id"],
            ["voice_profiles.workspace_id", "voice_profiles.id"],
        ),
        sa.CheckConstraint(
            "status IN ('generating', 'ready', 'failed')", name="content_plan_status"
        ),
    )
    op.create_index("ix_content_plans_workspace_id", "content_plans", ["workspace_id"])
    op.execute("ALTER TABLE content_plans ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE content_plans FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON content_plans USING (workspace_id = nullif("
        "current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif("
        "current_setting('app.workspace_id', true), ''))"
    )


def downgrade():
    op.drop_table("content_plans")
