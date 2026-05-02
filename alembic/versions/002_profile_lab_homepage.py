"""Profile & Lab Homepage tables

Revision ID: 002_profile_lab_homepage
Revises: 001_v2_platform_upgrade
Create Date: 2026-04-10

Creates: user_profiles, publications, projects, lab_news
All idempotent (IF NOT EXISTS).
"""
from alembic import op
import sqlalchemy as sa

revision = "002_profile_lab_homepage"
down_revision = "001_v2_platform_upgrade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── user_profiles (1-to-1 with users) ────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
            avatar_url          VARCHAR(500),
            title               VARCHAR(255),
            bio                 TEXT,
            orcid               VARCHAR(50),
            google_scholar_url  VARCHAR(500),
            researchgate_url    VARCHAR(500),
            website_url         VARCHAR(500),
            updated_at          TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_user_profiles_user ON user_profiles(user_id)"
    ))

    # ── publications ──────────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS publications (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title           VARCHAR(500) NOT NULL,
            authors         JSONB        NOT NULL,
            venue           VARCHAR(255) NOT NULL,
            year            INTEGER      NOT NULL,
            doi             VARCHAR(255),
            pdf_url         VARCHAR(500),
            abstract        TEXT,
            citation_count  INTEGER      NOT NULL DEFAULT 0,
            pub_type        VARCHAR(20)  NOT NULL,
            created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_publications_user ON publications(user_id)"
    ))

    # ── projects ──────────────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS projects (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title           VARCHAR(500) NOT NULL,
            description     TEXT         NOT NULL,
            role            VARCHAR(255) NOT NULL,
            funding_source  VARCHAR(255),
            start_date      DATE         NOT NULL,
            end_date        DATE,
            status          VARCHAR(20)  NOT NULL,
            collaborators   JSONB        NOT NULL DEFAULT '[]',
            created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id)"
    ))

    # ── lab_news ──────────────────────────────────────────────────────────────
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS lab_news (
            id              SERIAL PRIMARY KEY,
            lab_id          INTEGER      NOT NULL REFERENCES labs(id) ON DELETE CASCADE,
            author_id       INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title           VARCHAR(500) NOT NULL,
            content         TEXT         NOT NULL,
            published_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
            pinned          BOOLEAN      NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
        )
    """))
    # Composite index: lab_id + pinned DESC + published_at DESC for efficient homepage queries
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_lab_news_lab ON lab_news(lab_id, pinned DESC, published_at DESC)"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS lab_news"))
    conn.execute(sa.text("DROP TABLE IF EXISTS projects"))
    conn.execute(sa.text("DROP TABLE IF EXISTS publications"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_profiles"))
