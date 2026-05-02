"""Add lab_events table

Revision ID: 004_lab_events
Revises: 003_model_routing_overrides
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "004_lab_events"
down_revision = "003_model_routing_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lab_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lab_id", sa.Integer, sa.ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("event_date", sa.DateTime, nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False, server_default="seminar"),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lab_events")
