"""Usage ledger: separate the reservation (cost cap) from the actual provider cost.

Additive. usage_events gets the exact cost in micro-USD, the reservation that was held,
an `estimated` marker (true when the actual cost is not known from the provider's usage
field) and the model/usage details. usage_accounts gets the exact spent amount in
micro-USD; ai_spent_minor stays as its rounded-up mirror. Existing rows are marked
estimated until `python -m app.costs --apply` recalculates them from stored tokens.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "usage_events", sa.Column("cost_micro", sa.BigInteger(), nullable=False, server_default="0")
    )
    op.add_column(
        "usage_events",
        sa.Column("reserved_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "usage_events",
        sa.Column("estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "usage_events", sa.Column("model", sa.String(120), nullable=False, server_default="")
    )
    op.add_column(
        "usage_events",
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "usage_accounts",
        sa.Column("ai_spent_micro", sa.BigInteger(), nullable=False, server_default="0"),
    )
    # Old rows only know the booked cents (often the reservation cap): keep them, flagged.
    op.execute(
        "UPDATE usage_events SET cost_micro = cost_minor::bigint * 10000, estimated = true,"
        " reserved_minor = cost_minor"
    )
    op.execute("UPDATE usage_accounts SET ai_spent_micro = ai_spent_minor::bigint * 10000")


def downgrade():
    op.drop_column("usage_accounts", "ai_spent_micro")
    for column in ("details", "model", "estimated", "reserved_minor", "cost_micro"):
        op.drop_column("usage_events", column)
