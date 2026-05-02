"""Add idea_records table for idea_generation stage

Revision ID: 009_idea_records
Revises: 008_paper_code_repo
Create Date: 2026-04-19
"""
import sqlalchemy as sa
from alembic import op

revision = "009_idea_records"
down_revision = "008_paper_code_repo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "idea_records" not in inspector.get_table_names():
        op.create_table(
            "idea_records",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("topic_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("novelty_argument", sa.Text(), nullable=False),
            sa.Column("methodology_hint", sa.Text(), nullable=False),
            sa.Column("difficulty", sa.String(length=20), nullable=False, server_default="medium"),
            sa.Column("expected_impact", sa.String(length=20), nullable=False, server_default="medium"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    op.drop_table("idea_records")
