import sqlite3

conn = sqlite3.connect("school.db")
cursor = conn.cursor()

columns_to_add = [
    ("student_number", "TEXT"),
    ("birthday", "TEXT"),
    ("gender", "TEXT"),
    ("enrollment_date", "TEXT"),
    ("leaving_year", "TEXT"),
    ("boarding_status", "TEXT"),
    ("home_address", "TEXT"),
    ("mailing_address", "TEXT"),
    ("student_phone", "TEXT"),
    ("medical_info", "TEXT"),
    ("emergency_contact", "TEXT"),

    ("guardian1_name", "TEXT"),
    ("guardian1_relationship", "TEXT"),
    ("guardian1_phone", "TEXT"),
    ("guardian1_whatsapp", "TEXT"),
    ("guardian1_email", "TEXT"),

    ("guardian2_name", "TEXT"),
    ("guardian2_relationship", "TEXT"),
    ("guardian2_phone", "TEXT"),
    ("guardian2_whatsapp", "TEXT"),
    ("guardian2_email", "TEXT"),
]

for column_name, column_type in columns_to_add:
    try:
        cursor.execute(f"ALTER TABLE students ADD COLUMN {column_name} {column_type}")
        print(f"Added column: {column_name}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print(f"Column already exists: {column_name}")
        else:
            print(f"Could not add {column_name}: {e}")

conn.commit()
conn.close()

print("Students table update complete.")