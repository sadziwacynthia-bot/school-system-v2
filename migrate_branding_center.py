from utils.db import get_db, is_postgres


SQLITE_COLUMNS = {
    "stamp_data": "BLOB",
    "stamp_filename": "TEXT",
    "stamp_mime_type": "TEXT",

    "head_signature_data": "BLOB",
    "head_signature_filename": "TEXT",
    "head_signature_mime_type": "TEXT",

    "bursar_signature_data": "BLOB",
    "bursar_signature_filename": "TEXT",
    "bursar_signature_mime_type": "TEXT",

    "primary_color": "TEXT DEFAULT '#2563EB'",
    "secondary_color": "TEXT DEFAULT '#7C3AED'",
    "accent_color": "TEXT DEFAULT '#F59E0B'",

    "report_template": "TEXT DEFAULT 'classic'",

    "show_logo": "INTEGER DEFAULT 1",
    "show_stamp": "INTEGER DEFAULT 1",
    "show_head_signature": "INTEGER DEFAULT 1",
    "show_bursar_signature": "INTEGER DEFAULT 1",
    "show_position": "INTEGER DEFAULT 1",
    "show_attendance": "INTEGER DEFAULT 1",
    "show_conduct": "INTEGER DEFAULT 1"
}


POSTGRES_COLUMNS = {
    "stamp_data": "BYTEA",
    "stamp_filename": "TEXT",
    "stamp_mime_type": "TEXT",

    "head_signature_data": "BYTEA",
    "head_signature_filename": "TEXT",
    "head_signature_mime_type": "TEXT",

    "bursar_signature_data": "BYTEA",
    "bursar_signature_filename": "TEXT",
    "bursar_signature_mime_type": "TEXT",

    "primary_color": "TEXT DEFAULT '#2563EB'",
    "secondary_color": "TEXT DEFAULT '#7C3AED'",
    "accent_color": "TEXT DEFAULT '#F59E0B'",

    "report_template": "TEXT DEFAULT 'classic'",

    "show_logo": "BOOLEAN DEFAULT TRUE",
    "show_stamp": "BOOLEAN DEFAULT TRUE",
    "show_head_signature": "BOOLEAN DEFAULT TRUE",
    "show_bursar_signature": "BOOLEAN DEFAULT TRUE",
    "show_position": "BOOLEAN DEFAULT TRUE",
    "show_attendance": "BOOLEAN DEFAULT TRUE",
    "show_conduct": "BOOLEAN DEFAULT TRUE"
}


def get_existing_columns(cursor):
    """
    Return the current school_settings column names.
    Works with both SQLite and PostgreSQL.
    """
    if is_postgres():
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'school_settings'
            """
        )

        rows = cursor.fetchall()
        return {row["column_name"] for row in rows}

    cursor.execute("PRAGMA table_info(school_settings)")
    rows = cursor.fetchall()

    return {row["name"] for row in rows}


def migrate_branding_center():
    conn = get_db()
    cursor = conn.cursor()

    try:
        existing_columns = get_existing_columns(cursor)

        columns_to_add = (
            POSTGRES_COLUMNS
            if is_postgres()
            else SQLITE_COLUMNS
        )

        added_columns = []
        skipped_columns = []

        for column_name, column_definition in columns_to_add.items():
            if column_name in existing_columns:
                skipped_columns.append(column_name)
                continue

            query = (
                f"ALTER TABLE school_settings "
                f"ADD COLUMN {column_name} {column_definition}"
            )

            cursor.execute(query)
            added_columns.append(column_name)

        conn.commit()

        print("\n========================================")
        print("EDUTRACK BRANDING CENTER MIGRATION")
        print("========================================")

        if added_columns:
            print("\nAdded columns:")
            for column in added_columns:
                print(f"  + {column}")
        else:
            print("\nNo new columns were required.")

        if skipped_columns:
            print("\nAlready existing columns:")
            for column in skipped_columns:
                print(f"  - {column}")

        print("\nMigration completed successfully.")
        print("========================================\n")

    except Exception as error:
        conn.rollback()

        print("\nBranding Center migration failed.")
        print(f"Error: {error}\n")

        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    migrate_branding_center()