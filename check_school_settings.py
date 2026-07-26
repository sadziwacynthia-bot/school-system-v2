from utils.db import get_db, is_postgres


def check_school_settings():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = 'school_settings'
                ORDER BY ordinal_position
            """)

            rows = cursor.fetchall()

            print("\nSCHOOL_SETTINGS TABLE\n")

            for row in rows:
                print(dict(row))

        else:
            cursor.execute("PRAGMA table_info(school_settings)")

            rows = cursor.fetchall()

            print("\nSCHOOL_SETTINGS TABLE\n")

            for row in rows:
                print(tuple(row))

    finally:
        conn.close()


if __name__ == "__main__":
    check_school_settings()