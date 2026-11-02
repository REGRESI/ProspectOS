"""Reusable tenant-scoped voice profiles and backwards-compatible media/studio context."""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.UniqueConstraint("workspace_id", "id"),
    )
    op.create_index("ix_voice_profiles_workspace_id", "voice_profiles", ["workspace_id"])
    op.execute("ALTER TABLE voice_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE voice_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON voice_profiles USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), ''))"
    )
    op.add_column(
        "social_posts", sa.Column("studio_context", sa.JSON(), nullable=False, server_default="{}")
    )
    for name, size in (("title", 200), ("description", 2000), ("rights_note", 1000)):
        op.add_column("assets", sa.Column(name, sa.String(size), nullable=False, server_default=""))
    op.add_column("assets", sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column(
        "assets",
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id", name="asset_uploader")),
    )


def downgrade():
    op.drop_constraint("asset_uploader", "assets", type_="foreignkey")
    for name in ("uploaded_by", "tags", "rights_note", "description", "title"):
        op.drop_column("assets", name)
    op.drop_column("social_posts", "studio_context")
    op.drop_table("voice_profiles")
