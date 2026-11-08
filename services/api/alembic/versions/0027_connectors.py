"""M9: external outreach tool connections (opt-in, own risk), handoffs, inbound events.

Adds the 'tool' channel route and the 'tool_handoff' campaign step.
"""

import sqlalchemy as sa

from alembic import op

revision = "0027"
down_revision = "0026"
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
    op.drop_constraint("contact_channel_route", "contacts", type_="check")
    op.create_check_constraint(
        "contact_channel_route",
        "contacts",
        "channel_route IN ('linkedin', 'letter', 'tool', 'none')",
    )
    op.drop_constraint("flow_step_kind", "flow_steps", type_="check")
    op.create_check_constraint(
        "flow_step_kind",
        "flow_steps",
        "kind IN ('linkedin_task','letter','call_task','visit_task','email','wait','condition','tool_handoff')",
    )
    op.create_table(
        "connector_settings",
        *_base(),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acknowledged_by", sa.String(36)),
        sa.Column("acknowledged_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledgment_text", sa.String(1000), nullable=False, server_default=""),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "acknowledged_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )
    _rls("connector_settings")
    op.create_table(
        "outreach_connectors",
        *_base(),
        sa.Column("tool", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("secrets_ciphertext", sa.String(6000), nullable=False, server_default=""),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("inbound_secret_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("last_test_at", sa.DateTime(timezone=True)),
        sa.Column("last_test_ok", sa.Boolean()),
        sa.Column("last_error", sa.String(200), nullable=False, server_default=""),
        sa.UniqueConstraint("workspace_id", "tool"),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint(
            "tool IN ('heyreach','waalaxy','lgm','expandi','lemlist','webhook')",
            name="connector_tool",
        ),
    )
    _rls("outreach_connectors")
    op.create_table(
        "connector_handoffs",
        *_base(),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("tool", sa.String(20), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("linkedin_url", sa.String(500), nullable=False),
        sa.Column("external_ref", sa.String(300)),
        sa.Column("tool_contact_id", sa.String(100)),
        sa.Column("task_id", sa.String(36)),
        sa.Column("actor_id", sa.String(36)),
        sa.Column("last_event", sa.String(30), nullable=False, server_default=""),
        sa.Column("error", sa.String(200), nullable=False, server_default=""),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )
    _rls("connector_handoffs")
    op.create_index(
        "connector_one_active_handoff",
        "connector_handoffs",
        ["workspace_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('queued', 'handed_over')"),
    )
    op.create_table(
        "connector_events",
        *_base(),
        sa.Column("tool", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("contact_id", sa.String(36)),
        sa.Column("handoff_id", sa.String(36)),
        sa.Column("owner_id", sa.String(36)),
        sa.Column("event_id", sa.String(200)),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
    )
    _rls("connector_events")
    op.create_index(
        "connector_event_dedup",
        "connector_events",
        ["workspace_id", "tool", "event_id"],
        unique=True,
        postgresql_where=sa.text("event_id IS NOT NULL"),
    )


def downgrade():
    op.drop_table("connector_events")
    op.drop_table("connector_handoffs")
    op.drop_table("outreach_connectors")
    op.drop_table("connector_settings")
    op.execute("UPDATE flow_steps SET kind = 'linkedin_task' WHERE kind = 'tool_handoff'")
    op.drop_constraint("flow_step_kind", "flow_steps", type_="check")
    op.create_check_constraint(
        "flow_step_kind",
        "flow_steps",
        "kind IN ('linkedin_task','letter','call_task','visit_task','email','wait','condition')",
    )
    op.execute("UPDATE contacts SET channel_route = 'linkedin' WHERE channel_route = 'tool'")
    op.drop_constraint("contact_channel_route", "contacts", type_="check")
    op.create_check_constraint(
        "contact_channel_route", "contacts", "channel_route IN ('linkedin', 'letter', 'none')"
    )
