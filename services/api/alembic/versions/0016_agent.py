"""Job agent runs and morning autopilot settings (additive)."""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
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
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("instruction", sa.String(1000), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("estimate_minor", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'running', 'done', 'failed', 'cancelled')",
            name="agent_run_status",
        ),
    )
    op.create_index("ix_agent_runs_workspace_id", "agent_runs", ["workspace_id"])
    _rls("agent_runs")
    op.create_table(
        "autopilot_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("last_run_on", sa.Date()),
        sa.Column("updated_by", sa.String(36), nullable=False),
        sa.UniqueConstraint("workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "updated_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )
    _rls("autopilot_settings")


def downgrade():
    op.drop_table("autopilot_settings")
    op.drop_table("agent_runs")
