"""Check PostgreSQL connection and list databases."""
import psycopg2

configs = [
    {"host": "localhost", "port": 5432, "user": "postgres", "dbname": "postgres", "password": ""},
    {"host": "localhost", "port": 5432, "user": "postgres", "dbname": "postgres", "password": "postgres"},
    {"host": "localhost", "port": 5432, "user": "admin", "dbname": "postgres", "password": ""},
]

for cfg in configs:
    try:
        conn = psycopg2.connect(**cfg, connect_timeout=3)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        ver = cur.fetchone()[0]
        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
        dbs = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT current_user;")
        user = cur.fetchone()[0]
        conn.close()
        print(f"[OK] Connected as '{user}'")
        print(f"     Version : {ver[:70]}")
        print(f"     Databases: {dbs}")
        break
    except Exception as e:
        print(f"[FAIL] {cfg['user']}@{cfg['host']}:{cfg['port']} -> {e}")
