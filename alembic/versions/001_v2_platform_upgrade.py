"""v2 platform upgrade: new tables + additive columns

Revision ID: 001_v2_platform_upgrade
Revises:
Create Date: 2026-04-10

This migration is fully idempotent (uses IF NOT EXISTS / IF EXISTS).
"""
from alembic import op
import sqlalchemy as sa

revision = "001_v2_platform_upgrade"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. users ─────────────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            email         VARCHAR(255) NOT NULL UNIQUE,
            display_name  VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            plan          VARCHAR(20)  NOT NULL DEFAULT 'free',
            role          VARCHAR(20)  NOT NULL DEFAULT 'user',
            is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))
    # Idempotent: add role column if table already existed without it
    conn.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user'"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
    ))

    # ── 2. refresh_tokens ────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  VARCHAR(255) NOT NULL UNIQUE,
            expires_at  TIMESTAMP    NOT NULL,
            revoked     BOOLEAN      NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id)"
    ))

    # ── 3. password_reset_tokens ─────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  VARCHAR(255) NOT NULL UNIQUE,
            expires_at  TIMESTAMP    NOT NULL,
            used        BOOLEAN      NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))

    # ── 4. labs ──────────────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS labs (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(255) NOT NULL,
            description TEXT,
            owner_id    INTEGER      NOT NULL REFERENCES users(id),
            created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))

    # ── 5. lab_members ───────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS lab_members (
            id        SERIAL PRIMARY KEY,
            lab_id    INTEGER     NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
            user_id   INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role      VARCHAR(30) NOT NULL,
            joined_at TIMESTAMP   NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_lab_members_lab_user UNIQUE (lab_id, user_id)
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_lab_members_lab  ON lab_members(lab_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_lab_members_user ON lab_members(user_id)"
    ))

    # ── 6. lab_invitations ───────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS lab_invitations (
            id          SERIAL PRIMARY KEY,
            lab_id      INTEGER      NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
            email       VARCHAR(255) NOT NULL,
            role        VARCHAR(30)  NOT NULL,
            token_hash  VARCHAR(255) NOT NULL UNIQUE,
            expires_at  TIMESTAMP    NOT NULL,
            accepted    BOOLEAN      NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))

    # ── 7. github_repos ──────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS github_repos (
            id              SERIAL PRIMARY KEY,
            topic_id        INTEGER      NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            user_id         INTEGER      NOT NULL REFERENCES users(id),
            repo_url        VARCHAR(500) NOT NULL,
            encrypted_token TEXT,
            analysis_status VARCHAR(20)  NOT NULL DEFAULT 'pending',
            created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))

    # ── 8. code_analyses ─────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS code_analyses (
            id              SERIAL PRIMARY KEY,
            github_repo_id  INTEGER   NOT NULL REFERENCES github_repos(id) ON DELETE CASCADE,
            languages       JSONB,
            directory_tree  TEXT,
            key_modules     JSONB,
            readme_summary  TEXT,
            dependencies    JSONB,
            quality_issues  JSONB,
            progress_pct    INTEGER   NOT NULL DEFAULT 0,
            current_step    VARCHAR(100),
            triggered_at    TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMP
        )
    """))

    # ── 9. audit_logs ────────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id          BIGSERIAL PRIMARY KEY,
            user_id     INTEGER     REFERENCES users(id)  ON DELETE SET NULL,
            lab_id      INTEGER     REFERENCES labs(id)   ON DELETE SET NULL,
            topic_id    INTEGER     REFERENCES topics(id) ON DELETE SET NULL,
            event_type  VARCHAR(50) NOT NULL,
            event_data  JSONB,
            status      VARCHAR(20),
            created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_lab  ON audit_logs(lab_id, created_at DESC)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs(user_id, created_at DESC)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_type ON audit_logs(event_type)"
    ))

    # ── 10. usage_stats ──────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS usage_stats (
            id              SERIAL  PRIMARY KEY,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            month           DATE    NOT NULL,
            topics_created  INTEGER NOT NULL DEFAULT 0,
            pipeline_runs   INTEGER NOT NULL DEFAULT 0,
            papers_ingested INTEGER NOT NULL DEFAULT 0,
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_usage_stats_user_month UNIQUE (user_id, month)
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_usage_stats_user_month ON usage_stats(user_id, month)"
    ))

    # ── 11. Additive columns on existing tables ───────────────────────────────
    # topics
    conn.execute(sa.text(
        "ALTER TABLE topics ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE topics ADD COLUMN IF NOT EXISTS lab_id INTEGER REFERENCES labs(id)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE topics ADD COLUMN IF NOT EXISTS paper_type VARCHAR(50) NOT NULL DEFAULT 'survey'"
    ))

    # pipeline_runs
    conn.execute(sa.text(
        "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS lab_id INTEGER REFERENCES labs(id)"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # Remove additive columns first
    conn.execute(sa.text("ALTER TABLE pipeline_runs DROP COLUMN IF EXISTS lab_id"))
    conn.execute(sa.text("ALTER TABLE pipeline_runs DROP COLUMN IF EXISTS user_id"))
    conn.execute(sa.text("ALTER TABLE topics DROP COLUMN IF EXISTS paper_type"))
    conn.execute(sa.text("ALTER TABLE topics DROP COLUMN IF EXISTS lab_id"))
    conn.execute(sa.text("ALTER TABLE topics DROP COLUMN IF EXISTS user_id"))

    # Drop new tables in reverse dependency order
    conn.execute(sa.text("DROP TABLE IF EXISTS usage_stats"))
    conn.execute(sa.text("DROP TABLE IF EXISTS audit_logs"))
    conn.execute(sa.text("DROP TABLE IF EXISTS code_analyses"))
    conn.execute(sa.text("DROP TABLE IF EXISTS github_repos"))
    conn.execute(sa.text("DROP TABLE IF EXISTS lab_invitations"))
    conn.execute(sa.text("DROP TABLE IF EXISTS lab_members"))
    conn.execute(sa.text("DROP TABLE IF EXISTS labs"))
    conn.execute(sa.text("DROP TABLE IF EXISTS password_reset_tokens"))
    conn.execute(sa.text("DROP TABLE IF EXISTS refresh_tokens"))
    conn.execute(sa.text("DROP TABLE IF EXISTS users"))
