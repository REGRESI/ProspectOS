"""V3 M2: campaign builder steps, per-contact runs and due tasks."""

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
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
    op.create_table(
        "flow_steps",
        *_base(),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("route", sa.String(10), nullable=False),
        sa.Column("wait_days", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("template", sa.String(3000), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.UniqueConstraint("workspace_id", "campaign_id", "position"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('linkedin_task','letter','call_task','visit_task','email','wait','condition')",
            name="flow_step_kind",
        ),
        sa.CheckConstraint("route IN ('any','linkedin','letter')", name="flow_step_route"),
    )
    _rls("flow_steps")
    op.create_table(
        "flow_runs",
        *_base(),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("wait_until", sa.DateTime(timezone=True)),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column("stop_reason", sa.String(300), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "campaign_id", "contact_id"),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
    )
    _rls("flow_runs")
    op.create_index("ix_flow_runs_due", "flow_runs", ["workspace_id", "state", "next_due_at"])
    op.create_table(
        "flow_tasks",
        *_base(),
        sa.Column("run_id", sa.String(36)),
        sa.Column("campaign_id", sa.String(36)),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("step_position", sa.Integer()),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(3000), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("blocked_reason", sa.String(300), nullable=False),
        sa.Column("assignee_id", sa.String(36)),
        sa.Column("done_at", sa.DateTime(timezone=True)),
        sa.Column("done_by", sa.String(36)),
        sa.Column("note", sa.String(1000), nullable=False),
        sa.Column("origin", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["flow_runs.workspace_id", "flow_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "assignee_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "done_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )
    _rls("flow_tasks")
    op.create_index("ix_flow_tasks_due", "flow_tasks", ["workspace_id", "state", "due_at"])


def downgrade():
    op.drop_table("flow_tasks")
    op.drop_table("flow_runs")
    op.drop_table("flow_steps")
