"""Add model_routing_overrides to topics

Revision ID: 003_model_routing_overrides
Revises: 002_profile_lab_homepage
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "003_model_routing_overrides"
down_revision = "002_profile_lab_homepage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("topics") as batch_op:
        batch_op.add_column(
            sa.Column("model_routing_overrides", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("topics") as batch_op:
        batch_op.drop_column("model_routing_overrides")
