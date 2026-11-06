"""Workspace kind: production vs. demo (additive).

Demo workspaces are examples only: they never use real provider credentials and are
listed after production workspaces. Existing seed slugs are marked as demo.
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspaces",
        sa.Column("kind", sa.String(20), nullable=False, server_default="standard"),
    )
    op.create_check_constraint(
        "workspace_kind", "workspaces", "kind IN ('production', 'standard', 'demo')"
    )
    op.execute(
        "UPDATE workspaces SET kind = 'demo' WHERE slug IN ('cleanstar-demo', 'studio-demo')"
    )


def downgrade():
    op.drop_constraint("workspace_kind", "workspaces")
    op.drop_column("workspaces", "kind")
