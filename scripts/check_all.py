"""Check Gemini API and PostgreSQL connection."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

results = {}

# ── 1. Gemini ────────────────────────────────────────────────────────────────
print("=" * 55)
print("1. Testing Gemini...")
try:
    from app.core import llm as llm_module, config as cfg_module
    cfg_module.settings.llm_provider = "gemini"
    llm_module.reset_llm()
    resp = llm_module.get_llm().complete("You are a test assistant.", "Reply with exactly: OK", max_tokens=10)
    print(f"   [PASS] model={cfg_module.settings.gemini_model}  response={resp.strip()!r}")
    results["gemini"] = True
except Exception as e:
    print(f"   [FAIL] {type(e).__name__}: {str(e)[:120]}")
    results["gemini"] = False

# ── 2. PostgreSQL - try password 'abc' then 'abcabc' ────────────────────────
print("=" * 55)
print("2. Testing PostgreSQL...")
import psycopg2
from urllib.parse import urlparse

db_url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(db_url)
host, port, user = parsed.hostname, parsed.port or 5432, parsed.username
dbname = parsed.path.lstrip("/")

working_url = None
for pwd in [parsed.password, "abc", "abcabc"]:
    try:
        conn = psycopg2.connect(host=host, port=port, user=user, password=pwd,
                                dbname="postgres", connect_timeout=3)
        conn.close()
        working_url = f"postgresql://{user}:{pwd}@{host}:{port}/{dbname}"
        print(f"   [PASS] Connected with password='{pwd}'")
        results["pg_connect"] = True
        results["pg_password"] = pwd
        break
    except psycopg2.OperationalError as e:
        print(f"   [FAIL] password='{pwd}' -> {str(e).strip()[:80]}")
        results["pg_connect"] = False

# ── 3. Create DB + tables if connection succeeded ────────────────────────────
if results.get("pg_connect") and working_url:
    print("=" * 55)
    print("3. Setting up database...")
    try:
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        pwd = results["pg_password"]
        conn = psycopg2.connect(host=host, port=port, user=user, password=pwd,
                                dbname="postgres", connect_timeout=3)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{dbname}"')
            print(f"   [OK] Created database '{dbname}'")
        else:
            print(f"   [OK] Database '{dbname}' already exists")
        cur.close()
        conn.close()

        # Create tables
        from sqlalchemy import create_engine
        from app.core import database as db_module
        from app.core.database import Base
        db_module.engine = create_engine(working_url, echo=False, pool_pre_ping=True)
        from app.models import topic, paper, pipeline  # noqa
        Base.metadata.create_all(bind=db_module.engine)
        db_module.SessionLocal = __import__('sqlalchemy.orm', fromlist=['sessionmaker']).sessionmaker(
            autocommit=False, autoflush=False, bind=db_module.engine
        )
        # Verify
        with db_module.engine.connect() as c:
            from sqlalchemy import text
            tables = c.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )).fetchall()
        print(f"   [OK] Tables created: {[t[0] for t in tables]}")
        results["pg_tables"] = True

        # Update .env with correct password
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        with open(env_path) as f:
            content = f.read()
        # Replace DATABASE_URL line
        import re
        new_url = f"postgresql://{user}:{pwd}@{host}:{port}/{dbname}"
        content = re.sub(r"DATABASE_URL=postgresql://[^\n]+", f"DATABASE_URL={new_url}", content)
        with open(env_path, "w") as f:
            f.write(content)
        print(f"   [OK] .env updated with working DATABASE_URL")

    except Exception as e:
        print(f"   [FAIL] {type(e).__name__}: {e}")
        results["pg_tables"] = False

# ── Summary ──────────────────────────────────────────────────────────────────
print("=" * 55)
print("SUMMARY")
print("=" * 55)
icons = {True: "✅", False: "❌"}
print(f"  Gemini ({cfg_module.settings.gemini_model}): {icons[results.get('gemini', False)]}")
print(f"  PostgreSQL connect:  {icons[results.get('pg_connect', False)]}")
print(f"  PostgreSQL tables:   {icons[results.get('pg_tables', False)]}")
if results.get("pg_connect"):
    print(f"\n  Working DATABASE_URL: postgresql://{user}:{results['pg_password']}@{host}:{port}/{dbname}")
