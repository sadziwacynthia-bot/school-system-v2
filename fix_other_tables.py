import sqlite3

conn = sqlite3.connect("school.db")
cursor = conn.cursor()

guardian_columns = [
    ("relationship", "TEXT"),
    ("whatsapp", "TEXT"),
    ("email", "TEXT"),
]

fee_columns = [
    ("term_name", "TEXT"),
]

for column_name, column_type in guardian_columns:
    try:
        cursor.execute(f"ALTER TABLE guardians ADD COLUMN {column_name} {column_type}")
        print(f"Added guardians column: {column_name}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"Guardians column already exists: {column_name}")
        else:
            print(f"Could not add guardians column {column_name}: {e}")

for column_name, column_type in fee_columns:
    try:
        cursor.execute(f"ALTER TABLE fees ADD COLUMN {column_name} {column_type}")
        print(f"Added fees column: {column_name}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"Fees column already exists: {column_name}")
        else:
            print(f"Could not add fees column {column_name}: {e}")

conn.commit()
conn.close()

print("Other tables update complete.")