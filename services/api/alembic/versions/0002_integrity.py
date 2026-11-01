"""Database-level invariants complement request validation."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
CONSTRAINTS = [
    ("memberships", "membership_role", "role IN ('owner','admin','editor','approver','analyst')"),
    ("contacts", "contact_version", "version >= 1"),
    ("contacts", "contact_status", "status IN ('new','qualified','contacted','archived')"),
    ("deals", "deal_amount", "amount >= 0"),
    (
        "deals",
        "deal_stage",
        "stage IN ('new','qualified','contacted','conversation','proposal','won','lost')",
    ),
    (
        "social_posts",
        "post_revision",
        "version >= 1 AND (approved_revision IS NULL OR approved_revision = version)",
    ),
    (
        "social_posts",
        "post_schedule",
        "state != 'scheduled' OR (scheduled_at IS NOT NULL AND approved_revision = version)",
    ),
]


def upgrade():
    for table, name, expression in CONSTRAINTS:
        op.create_check_constraint(name, table, expression)


def downgrade():
    for table, name, _expression in reversed(CONSTRAINTS):
        op.drop_constraint(name, table, type_="check")
