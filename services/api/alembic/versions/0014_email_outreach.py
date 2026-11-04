"""Mailboxes, outbound email messages/events, legal basis country (additive)."""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
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
        "mailboxes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("username", sa.String(254), nullable=False),
        sa.Column("ciphertext", sa.String(4000), nullable=False),
        sa.Column("smtp_host", sa.String(253), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False),
        sa.Column("smtp_security", sa.String(10), nullable=False),
        sa.Column("imap_host", sa.String(253), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False),
        sa.Column("signature", sa.String(1000), nullable=False),
        sa.Column("sender_footer", sa.String(1000), nullable=False),
        sa.Column("ramp_start", sa.Date(), nullable=False),
        sa.Column("ramp_start_limit", sa.Integer(), nullable=False),
        sa.Column("ramp_step", sa.Integer(), nullable=False),
        sa.Column("daily_max", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("window_end", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("paused_reason", sa.String(300), nullable=False),
        sa.Column("last_error", sa.String(100), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True)),
        sa.Column("imap_last_uid", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("workspace_id", "email"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "created_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.CheckConstraint("status IN ('active', 'paused', 'error')", name="mailbox_status"),
        sa.CheckConstraint("smtp_security IN ('ssl', 'starttls')", name="mailbox_security"),
    )
    op.create_index("ix_mailboxes_workspace_id", "mailboxes", ["workspace_id"])
    _rls("mailboxes")
    op.create_table(
        "email_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mailbox_id", sa.String(36), nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36)),
        sa.Column("draft_id", sa.String(36), nullable=False),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("step_position", sa.Integer(), nullable=False),
        sa.Column("to_email", sa.String(254), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("message_id", sa.String(300)),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("unsubscribe_hash", sa.String(64), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(100), nullable=False),
        sa.UniqueConstraint("workspace_id", "draft_id", "draft_revision"),
        sa.UniqueConstraint("unsubscribe_hash"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "mailbox_id"], ["mailboxes.workspace_id", "mailboxes.id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"], ["campaigns.workspace_id", "campaigns.id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "draft_id"], ["message_drafts.workspace_id", "message_drafts.id"]
        ),
        sa.CheckConstraint(
            "state IN ('scheduled', 'sending', 'sent', 'bounced', 'replied', 'unsubscribed', "
            "'complained', 'failed', 'blocked', 'cancelled', 'ambiguous')",
            name="email_message_state",
        ),
    )
    op.create_index("ix_email_messages_workspace_id", "email_messages", ["workspace_id"])
    op.create_index("ix_email_messages_message_id", "email_messages", ["message_id"])
    _rls("email_messages")
    op.add_column(
        "consents", sa.Column("country", sa.String(2), nullable=False, server_default="DE")
    )
    op.add_column("consents", sa.Column("evidence_url", sa.String(2000)))


def downgrade():
    op.drop_column("consents", "evidence_url")
    op.drop_column("consents", "country")
    op.drop_table("email_messages")
    op.drop_table("mailboxes")
