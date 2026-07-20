import os
import psycopg2

database_url = os.environ.get("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL environment variable not found.")

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

conn = psycopg2.connect(database_url)
cur = conn.cursor()

try:
    cur.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS marked_by_user_id INTEGER;
    """)

    cur.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS marked_by_name VARCHAR(255);
    """)

    cur.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS marked_at TIMESTAMP;
    """)

    cur.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
    """)

    conn.commit()
    print("✅ Attendance table updated successfully!")

finally:
    cur.close()
    conn.close()