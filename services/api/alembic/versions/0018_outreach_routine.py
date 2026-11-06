"""LinkedIn day routine: per-contact outreach stage and per-workspace outreach settings.

Additive. Stages: new (neu), sent (gesendet), connected (verbunden), replied
(geantwortet), meeting (Termin), not_interested (kein Interesse). Existing manual
LinkedIn actions are used to backfill the stage once.
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

STAGES = "('new', 'sent', 'connected', 'replied', 'meeting', 'not_interested')"


def upgrade():
    op.add_column(
        "contacts",
        sa.Column("outreach_stage", sa.String(20), nullable=False, server_default="new"),
    )
    op.add_column("contacts", sa.Column("outreach_stage_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("contact_outreach_stage", "contacts", f"outreach_stage IN {STAGES}")
    # Backfill from self-reported manual LinkedIn actions (highest stage wins).
    op.execute(
        """
        UPDATE contacts c SET outreach_stage = s.stage, outreach_stage_at = s.at
        FROM (
          SELECT contact_id, workspace_id,
            CASE MAX(CASE
                WHEN action = 'message' AND state = 'replied' THEN 3
                WHEN action = 'connection_request' AND state = 'accepted' THEN 2
                WHEN action = 'connection_request' AND state IN ('sent', 'declined') THEN 1
                ELSE 0 END)
              WHEN 3 THEN 'replied' WHEN 2 THEN 'connected' WHEN 1 THEN 'sent' ELSE 'new' END
              AS stage,
            MAX(created_at) AS at
          FROM linkedin_actions WHERE channel = 'manual'
          GROUP BY contact_id, workspace_id
        ) s
        WHERE c.id = s.contact_id AND c.workspace_id = s.workspace_id AND s.stage <> 'new'
        """
    )
    op.create_table(
        "outreach_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("address_form", sa.String(3), nullable=False, server_default="sie"),
        sa.Column("sender_name", sa.String(80), nullable=False, server_default=""),
        sa.Column("sender_company", sa.String(80), nullable=False, server_default=""),
        sa.Column(
            "offer", sa.String(120), nullable=False, server_default="Büro-Unterhaltsreinigung"
        ),
        sa.Column("region", sa.String(60), nullable=False, server_default="der Ortenau"),
        sa.Column("updated_by", sa.String(36)),
        sa.UniqueConstraint("workspace_id"),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint("daily_limit BETWEEN 5 AND 10", name="outreach_daily_limit"),
        sa.CheckConstraint("address_form IN ('sie', 'du')", name="outreach_address_form"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "updated_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )
    # Second follow-up (day 7) in the day queue; widening a CHECK keeps all existing rows.
    op.drop_constraint("outreach_queue_kind", "outreach_queue_items")
    op.create_check_constraint(
        "outreach_queue_kind",
        "outreach_queue_items",
        "kind IN ('connect', 'message', 'followup', 'followup2')",
    )
    op.execute("ALTER TABLE outreach_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE outreach_settings FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON outreach_settings USING (workspace_id = nullif("
        "current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif("
        "current_setting('app.workspace_id', true), ''))"
    )


def downgrade():
    op.execute("DELETE FROM outreach_queue_items WHERE kind = 'followup2'")
    op.drop_constraint("outreach_queue_kind", "outreach_queue_items")
    op.create_check_constraint(
        "outreach_queue_kind",
        "outreach_queue_items",
        "kind IN ('connect', 'message', 'followup')",
    )
    op.drop_table("outreach_settings")
    op.drop_constraint("contact_outreach_stage", "contacts")
    op.drop_column("contacts", "outreach_stage_at")
    op.drop_column("contacts", "outreach_stage")
