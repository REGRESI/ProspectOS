"""OSM discovery context, per-workspace geocode cache and source-backed company facts."""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

POLICY = (
    "CREATE POLICY tenant_isolation ON {t} USING (workspace_id = nullif(current_setting("
    "'app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif(current_setting("
    "'app.workspace_id', true), ''))"
)


def upgrade():
    op.add_column(
        "discovery_runs", sa.Column("criteria", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column(
        "discovery_runs", sa.Column("meta", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_table(
        "geocode_cache",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query_key", sa.String(300), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("source_url", sa.String(300), nullable=False),
        sa.UniqueConstraint("workspace_id", "query_key"),
    )
    op.create_index("ix_geocode_cache_workspace_id", "geocode_cache", ["workspace_id"])
    op.execute("ALTER TABLE geocode_cache ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE geocode_cache FORCE ROW LEVEL SECURITY")
    op.execute(POLICY.format(t="geocode_cache"))
    op.add_column(
        "company_facts",
        sa.Column("source_kind", sa.String(40), nullable=False, server_default="manual"),
    )
    op.add_column("company_facts", sa.Column("source_id", sa.String(64)))
    op.add_column("company_facts", sa.Column("actor_id", sa.String(36)))
    op.create_foreign_key(
        "company_fact_actor",
        "company_facts",
        "memberships",
        ["workspace_id", "actor_id"],
        ["workspace_id", "user_id"],
    )


def downgrade():
    op.drop_constraint("company_fact_actor", "company_facts", type_="foreignkey")
    for name in ("actor_id", "source_id", "source_kind"):
        op.drop_column("company_facts", name)
    op.drop_table("geocode_cache")
    op.drop_column("discovery_runs", "meta")
    op.drop_column("discovery_runs", "criteria")
