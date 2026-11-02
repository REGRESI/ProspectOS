"""Verified external identity bindings and tenant-scoped invitations."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("auth_subject", sa.String(500), nullable=True))
    op.create_unique_constraint("users_auth_subject_key", "users", ["auth_subject"])
    op.add_column(
        "auth_sessions",
        sa.Column("auth_provider", sa.String(20), nullable=False, server_default="demo"),
    )
    op.create_table(
        "workspace_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.CheckConstraint("role IN ('admin','editor','approver','analyst')", name="invite_role"),
    )
    op.create_index("ix_workspace_invites_workspace_id", "workspace_invites", ["workspace_id"])
    op.execute("ALTER TABLE workspace_invites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspace_invites FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON workspace_invites USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), ''))"
    )
    # The table owner can service the narrow capability lookup even with FORCE RLS.
    # The application role cannot assume the owner role and receives no broad policy.
    bind = op.get_bind()
    policy = bind.scalar(
        sa.text(
            "SELECT format('CREATE POLICY invitation_capability_lookup ON public.workspace_invites TO %I USING (true)', current_user)"
        )
    )
    op.execute(policy)
    op.execute("""CREATE FUNCTION public.invitation_workspace(capability_hash text) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        AS $$ SELECT workspace_id FROM public.workspace_invites
        WHERE token_hash = capability_hash AND expires_at > now() AND accepted_at IS NULL LIMIT 1 $$""")
    op.execute("REVOKE ALL ON FUNCTION public.invitation_workspace(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.invitation_workspace(text) TO prospectos_app")
    op.create_table(
        "auth_rate_buckets",
        sa.Column("bucket", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("auth_rate_buckets")
    op.execute("DROP FUNCTION public.invitation_workspace(text)")
    op.drop_table("workspace_invites")
    op.drop_constraint("users_auth_subject_key", "users", type_="unique")
    op.drop_column("users", "auth_subject")
    op.drop_column("auth_sessions", "auth_provider")
