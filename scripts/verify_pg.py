import psycopg2
conn = psycopg2.connect(host="localhost", port=5432, user="postgres", password="abc", dbname="research_platform")
cur = conn.cursor()
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables ({len(tables)}): {tables}")
cur.execute("SELECT version()")
print("PG version:", cur.fetchone()[0][:50])
conn.close()
