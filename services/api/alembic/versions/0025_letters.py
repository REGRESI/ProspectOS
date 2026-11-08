"""V3 M4: letter settings and letters (DIN 5008, QR code per company)."""

import sqlalchemy as sa

from alembic import op

revision = "0025"
down_revision = "0024"
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
    text = sa.String
    op.create_table(
        "letter_settings",
        *_base(),
        sa.Column("sender_name", text(80), nullable=False),
        sa.Column("sender_company", text(80), nullable=False),
        sa.Column("sender_street", text(120), nullable=False),
        sa.Column("sender_city", text(120), nullable=False),
        sa.Column("sender_phone", text(40), nullable=False),
        sa.Column("sender_email", text(120), nullable=False),
        sa.Column("sender_web", text(120), nullable=False),
        sa.Column("qr_target_url", text(500), nullable=False),
        sa.Column("qr_caption", text(120), nullable=False),
        sa.Column("subject", text(120), nullable=False),
        sa.Column("body_template", text(3000), nullable=False),
        sa.Column("closing", text(80), nullable=False),
        sa.Column("print_service_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("workspace_id"),
    )
    _rls("letter_settings")
    op.create_table(
        "letters",
        *_base(),
        sa.Column("contact_id", text(36), nullable=False),
        sa.Column("company_id", text(36)),
        sa.Column("task_id", text(36)),
        sa.Column("code", text(20), nullable=False),
        sa.Column("recipient", sa.JSON(), nullable=False),
        sa.Column("subject", text(120), nullable=False),
        sa.Column("body", text(3000), nullable=False),
        sa.Column("qr_url", text(600), nullable=False),
        sa.Column("state", text(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("approved_by", text(36)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("printed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "company_id"], ["companies.workspace_id", "companies.id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "approved_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.CheckConstraint(
            "state IN ('draft','approved','printed','cancelled')", name="letter_state"
        ),
    )
    _rls("letters")


def downgrade():
    op.drop_table("letters")
    op.drop_table("letter_settings")
