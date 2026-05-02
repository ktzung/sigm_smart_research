"""Try to find working PostgreSQL credentials."""
import psycopg2

# Common passwords to try
passwords = ["", "postgres", "admin", "password", "123456", "root", "1234"]
users = ["postgres", "admin"]

print("Scanning for working PostgreSQL credentials...")
found = False
for user in users:
    for pwd in passwords:
        try:
            conn = psycopg2.connect(
                host="localhost", port=5432,
                user=user, password=pwd,
                dbname="postgres", connect_timeout=2
            )
            cur = conn.cursor()
            cur.execute("SELECT current_user, version();")
            row = cur.fetchone()
            cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
            dbs = [r[0] for r in cur.fetchall()]
            conn.close()
            print(f"\n[FOUND] user={user!r}  password={pwd!r}")
            print(f"        version: {row[1][:60]}")
            print(f"        databases: {dbs}")
            print(f"\nUse this DATABASE_URL:")
            print(f"  DATABASE_URL=postgresql://{user}:{pwd}@localhost:5432/<your_db>")
            found = True
            break
        except psycopg2.OperationalError:
            pass
    if found:
        break

if not found:
    print("\nCould not auto-detect credentials.")
    print("Please provide your PostgreSQL password:")
    print("  python scripts/check_pg2.py")
    print("\nOr set manually in .env:")
    print("  DATABASE_URL=postgresql://YOUR_USER:YOUR_PASSWORD@localhost:5432/research_platform")
