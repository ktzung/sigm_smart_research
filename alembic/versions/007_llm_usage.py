"""Add llm_usage_records table

Revision ID: 007_llm_usage
Revises: 006_lab_slides
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "007_llm_usage"
down_revision = "006_lab_slides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS llm_usage_records (
            id                BIGSERIAL PRIMARY KEY,
            user_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
            topic_id          INTEGER REFERENCES topics(id) ON DELETE SET NULL,
            stage             VARCHAR(100) NOT NULL,
            provider          VARCHAR(50)  NOT NULL,
            model             VARCHAR(100) NOT NULL,
            prompt_tokens     INTEGER      NOT NULL DEFAULT 0,
            completion_tokens INTEGER      NOT NULL DEFAULT 0,
            total_tokens      INTEGER      NOT NULL DEFAULT 0,
            cost_usd          FLOAT        NOT NULL DEFAULT 0.0,
            latency_ms        INTEGER,
            created_at        TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_llm_usage_user    ON llm_usage_records(user_id, created_at DESC)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_llm_usage_topic   ON llm_usage_records(topic_id, created_at DESC)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage_records(created_at DESC)"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS llm_usage_records"))
