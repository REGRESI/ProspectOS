"""V3 M3: reactions inbox and reference codes for letters/QR scans.

``ref_codes`` has RLS enabled (not forced): the application role only sees its own
workspace, while the SECURITY DEFINER function ``resolve_ref_code`` (owned by the
migrator) resolves one code for the public scan endpoint and returns ids only.
"""

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

POLICY = (
    "CREATE POLICY tenant_isolation ON {t} USING (workspace_id = nullif(current_setting("
    "'app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif(current_setting("
    "'app.workspace_id', true), ''))"
)


def _base():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "reactions",
        *_base(),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("text", sa.String(4000), nullable=False),
        sa.Column("code", sa.String(20)),
        sa.Column("source_ref", sa.String(300)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_by", sa.String(36)),
        sa.Column("status_at", sa.DateTime(timezone=True)),
        sa.Column("actor_id", sa.String(36)),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "status_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        sa.CheckConstraint(
            "status IN ('new','answered','meeting','not_interested')", name="reaction_status"
        ),
    )
    op.create_index("ix_reactions_workspace_id", "reactions", ["workspace_id"])
    op.create_index(
        "ix_reactions_contact", "reactions", ["workspace_id", "contact_id", "created_at"]
    )
    op.execute("ALTER TABLE reactions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE reactions FORCE ROW LEVEL SECURITY")
    op.execute(POLICY.format(t="reactions"))
    op.create_table(
        "ref_codes",
        *_base(),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column("target_url", sa.String(500), nullable=False, server_default=""),
        sa.UniqueConstraint("workspace_id", "company_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_ref_codes_workspace_id", "ref_codes", ["workspace_id"])
    op.execute("ALTER TABLE ref_codes ENABLE ROW LEVEL SECURITY")
    op.execute(POLICY.format(t="ref_codes"))
    op.execute(
        """
        CREATE FUNCTION resolve_ref_code(p_code text)
        RETURNS TABLE (workspace_id varchar, company_id varchar, target_url varchar)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
          SELECT r.workspace_id, r.company_id, r.target_url FROM ref_codes r WHERE r.code = p_code
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION resolve_ref_code(text) FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prospectos_app') THEN "
        "GRANT EXECUTE ON FUNCTION resolve_ref_code(text) TO prospectos_app; END IF; END $$"
    )


def downgrade():
    op.execute("DROP FUNCTION IF EXISTS resolve_ref_code(text)")
    op.drop_table("ref_codes")
    op.drop_table("reactions")
