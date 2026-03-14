"""create usage_metrics table

Revision ID: 0017_usage_metrics
Revises: 0016_previous_migration
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0017_usage_metrics"
down_revision = None  # Set this to your last migration ID
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usage_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_user_type_date", "usage_metrics", ["user_id", "metric_type", "created_at"])
    op.create_index("ix_usage_user_id", "usage_metrics", ["user_id"])


def downgrade():
    op.drop_index("ix_usage_user_id", table_name="usage_metrics")
    op.drop_index("ix_usage_user_type_date", table_name="usage_metrics")
    op.drop_table("usage_metrics")