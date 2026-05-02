"""Add paper_abstract, paper_keywords, authors_info columns to topics table."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import psycopg2

conn = psycopg2.connect(host="localhost", port=5432, user="postgres",
                        password="abc", dbname="research_platform")
cur = conn.cursor()

migrations = [
    "ALTER TABLE topics ADD COLUMN IF NOT EXISTS paper_abstract TEXT",
    "ALTER TABLE topics ADD COLUMN IF NOT EXISTS paper_keywords VARCHAR(500)",
    "ALTER TABLE topics ADD COLUMN IF NOT EXISTS authors_info JSONB",
]
for sql in migrations:
    cur.execute(sql)
    print(f"OK: {sql}")

conn.commit()
cur.close()
conn.close()
print("Migration complete.")
