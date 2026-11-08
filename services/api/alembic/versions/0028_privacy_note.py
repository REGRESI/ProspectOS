"""M9e: Art. 14 GDPR notice on the first letter to a company.

Additive: one column with an empty default.
"""

import sqlalchemy as sa

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "letters",
        sa.Column("privacy_note", sa.String(700), nullable=False, server_default=""),
    )


def downgrade():
    op.drop_column("letters", "privacy_note")
