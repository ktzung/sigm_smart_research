"""Add code_repo fields to papers table

Revision ID: 008_paper_code_repo
Revises: 007_llm_usage
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "008_paper_code_repo"
down_revision = "007_llm_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE papers ADD COLUMN IF NOT EXISTS code_repo_url   TEXT"))
    conn.execute(sa.text("ALTER TABLE papers ADD COLUMN IF NOT EXISTS code_repo_stars INTEGER"))
    conn.execute(sa.text("ALTER TABLE papers ADD COLUMN IF NOT EXISTS code_framework  VARCHAR(50)"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE papers DROP COLUMN IF EXISTS code_repo_url"))
    conn.execute(sa.text("ALTER TABLE papers DROP COLUMN IF EXISTS code_repo_stars"))
    conn.execute(sa.text("ALTER TABLE papers DROP COLUMN IF EXISTS code_framework"))
