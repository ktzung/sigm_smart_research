"""Add lab_slides table

Revision ID: 006_lab_slides
Revises: 005_remote_execution
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "006_lab_slides"
down_revision = "005_remote_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS lab_slides (
            id          SERIAL PRIMARY KEY,
            lab_id      INTEGER NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
            image_url   VARCHAR(500) NOT NULL,
            caption     VARCHAR(500),
            location    VARCHAR(255),
            sort_order  INTEGER NOT NULL DEFAULT 0,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_lab_slides_lab ON lab_slides(lab_id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS lab_slides"))
