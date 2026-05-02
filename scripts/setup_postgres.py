"""
Setup PostgreSQL database for Research Platform.
Run this once after setting DATABASE_URL in .env

Usage:
    python scripts/setup_postgres.py
    python scripts/setup_postgres.py --url "postgresql://user:pass@localhost:5432/mydb"
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

def parse_pg_url(url: str):
    """Parse postgresql://user:pass@host:port/dbname"""
    from urllib.parse import urlparse
    p = urlparse(url)
    return {
        "user": p.username,
        "password": p.password or "",
        "host": p.hostname,
        "port": p.port or 5432,
        "dbname": p.path.lstrip("/"),
    }


def create_database_if_not_exists(cfg: dict):
    """Connect to 'postgres' default DB and create target DB if missing."""
    admin_cfg = {**cfg, "dbname": "postgres"}
    conn = psycopg2.connect(**admin_cfg, connect_timeout=5)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (cfg["dbname"],))
    exists = cur.fetchone()
    if not exists:
        cur.execute(f'CREATE DATABASE "{cfg["dbname"]}"')
        print(f"[OK] Created database: {cfg['dbname']}")
    else:
        print(f"[OK] Database already exists: {cfg['dbname']}")
    cur.close()
    conn.close()


def test_connection(url: str):
    """Test final connection and create all tables."""
    from app.core.database import init_db
    from app.core import config as cfg_module
    cfg_module.settings.database_url = url
    # Reinitialize engine with new URL
    from app.core import database as db_module
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    db_module.engine = create_engine(url, echo=False)
    db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_module.engine)
    init_db()
    print("[OK] All tables created successfully")
    # Quick sanity check
    with db_module.engine.connect() as conn:
        from sqlalchemy import text
        result = conn.execute(text("SELECT COUNT(*) FROM topics"))
        count = result.scalar()
        print(f"[OK] topics table accessible (rows: {count})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Override DATABASE_URL")
    args = parser.parse_args()

    db_url = args.url or os.environ.get("DATABASE_URL", "")
    if not db_url or "YOUR_PASSWORD" in db_url:
        print("[ERROR] DATABASE_URL not set or still has placeholder.")
        print("  Edit .env and set: DATABASE_URL=postgresql://user:password@localhost:5432/research_platform")
        sys.exit(1)

    if not db_url.startswith("postgresql"):
        print(f"[INFO] DATABASE_URL is not PostgreSQL ({db_url[:30]}...), skipping.")
        sys.exit(0)

    print(f"Setting up PostgreSQL: {db_url.split('@')[-1]}")  # hide credentials in output
    cfg = parse_pg_url(db_url)

    try:
        create_database_if_not_exists(cfg)
        test_connection(db_url)
        print("\n[SUCCESS] PostgreSQL is ready. Update .env and start the server.")
    except psycopg2.OperationalError as e:
        print(f"\n[ERROR] Connection failed: {e}")
        print("\nCheck:")
        print("  1. PostgreSQL is running")
        print("  2. Username and password are correct")
        print("  3. User has CREATE DATABASE permission")
        sys.exit(1)


if __name__ == "__main__":
    main()
