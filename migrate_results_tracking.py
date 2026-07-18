from app import app, get_db


NEW_COLUMNS = {
    "academic_year": "INTEGER",
    "teacher_comment": "TEXT",
    "entered_by_user_id": "INTEGER",
    "entered_by_name": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT"
}


def get_existing_columns(conn):
    module_name = conn.__class__.__module__.lower()

    if "sqlite" in module_name:
        rows = conn.execute(
            "PRAGMA table_info(results)"
        ).fetchall()

        return {
            row["name"] if hasattr(row, "keys") else row[1]
            for row in rows
        }

    cursor = conn.cursor()

    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'results'
    """)

    return {
        row["column_name"] if isinstance(row, dict) else row[0]
        for row in cursor.fetchall()
    }


with app.app_context():
    conn = get_db()
    cursor = conn.cursor()

    try:
        existing_columns = get_existing_columns(conn)

        print("\nCURRENT RESULTS COLUMNS")
        print("=" * 60)

        for column_name in sorted(existing_columns):
            print(column_name)

        print("\nADDING NEW COLUMNS")
        print("=" * 60)

        for column_name, column_type in NEW_COLUMNS.items():

            if column_name in existing_columns:
                print(f"SKIPPED: {column_name} already exists")
                continue

            cursor.execute(
                f"""
                ALTER TABLE results
                ADD COLUMN {column_name} {column_type}
                """
            )

            print(f"ADDED: {column_name}")

        conn.commit()

        print("=" * 60)
        print("Results migration completed successfully.")

    except Exception as error:
        conn.rollback()

        print("=" * 60)
        print(f"Migration failed: {error}")

        raise

    finally:
        conn.close()
