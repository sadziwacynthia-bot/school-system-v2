import os
import psycopg2

database_url = os.environ.get("DATABASE_URL")

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

conn = psycopg2.connect(database_url)
cur = conn.cursor()

cur.execute("""
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'results'
ORDER BY ordinal_position;
""")

print("\nRESULTS TABLE SCHEMA\n")

for column_name, data_type in cur.fetchall():
    print(f"{column_name:<25} {data_type}")

cur.close()
conn.close()