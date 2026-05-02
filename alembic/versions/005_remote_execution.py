"""Add ssh_servers and remote_executions tables

Revision ID: 005_remote_execution
Revises: 004_lab_events
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "005_remote_execution"
down_revision = "004_lab_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS ssh_servers (
            id                   SERIAL PRIMARY KEY,
            user_id              INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name                 VARCHAR(100) NOT NULL,
            host                 VARCHAR(255) NOT NULL,
            username             VARCHAR(100) NOT NULL,
            encrypted_key_path   TEXT         NOT NULL,
            encrypted_passphrase TEXT,
            gpu_type             VARCHAR(100) NOT NULL DEFAULT 'Unknown',
            scheduler_type       VARCHAR(20)  NOT NULL DEFAULT 'standalone',
            created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ssh_servers_user_name UNIQUE (user_id, name)
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_ssh_servers_user ON ssh_servers(user_id)"
    ))

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS remote_executions (
            id               SERIAL PRIMARY KEY,
            topic_id         INTEGER     NOT NULL UNIQUE REFERENCES topics(id) ON DELETE CASCADE,
            ssh_server_id    INTEGER     REFERENCES ssh_servers(id) ON DELETE SET NULL,
            execution_status VARCHAR(20) NOT NULL DEFAULT 'generated',
            created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMP   NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_remote_executions_topic ON remote_executions(topic_id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS remote_executions"))
    conn.execute(sa.text("DROP TABLE IF EXISTS ssh_servers"))
