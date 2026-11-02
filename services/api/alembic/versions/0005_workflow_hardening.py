"""Source review, email approvals and actual dispatch timestamps."""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None
COLUMNS = [
    ("companies", sa.Column("website", sa.String(2000), nullable=True)),
    ("companies", sa.Column("provenance", sa.JSON(), nullable=False, server_default="{}")),
    (
        "contacts",
        sa.Column("source_reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
    ),
    ("jobs", sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True)),
    ("social_posts", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)),
    ("message_drafts", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")),
    ("message_drafts", sa.Column("approved_revision", sa.Integer(), nullable=True)),
    ("message_drafts", sa.Column("subject", sa.String(200), nullable=False, server_default="")),
    ("message_drafts", sa.Column("state", sa.String(30), nullable=False, server_default="draft")),
]


def upgrade():
    for table, column in COLUMNS:
        op.add_column(table, column)
    op.create_check_constraint(
        "draft_revision",
        "message_drafts",
        "revision >= 1 AND (approved_revision IS NULL OR approved_revision = revision)",
    )


def downgrade():
    op.drop_constraint("draft_revision", "message_drafts", type_="check")
    for table, column in reversed(COLUMNS):
        op.drop_column(table, column.name)
