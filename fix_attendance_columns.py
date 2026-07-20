import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL was not found.")

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

conn = None

try:
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    cursor.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS marked_by_user_id INTEGER;
    """)

    cursor.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS marked_by_name VARCHAR(255);
    """)

    cursor.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS marked_at TIMESTAMP;
    """)

    cursor.execute("""
        ALTER TABLE attendance
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
    """)

    cursor.execute("""
        UPDATE attendance
        SET marked_at = CURRENT_TIMESTAMP
        WHERE marked_at IS NULL;
    """)

    cursor.execute("""
        UPDATE attendance
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL;
    """)

    conn.commit()

    print("Attendance table updated successfully.")

except Exception as error:
    if conn:
        conn.rollback()

    print("Attendance migration failed:")
    print(error)

finally:
    if conn:
        conn.close()