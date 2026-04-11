import sqlite3

conn = sqlite3.connect("school.db")
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE fees ADD COLUMN term_name TEXT")
    print("term_name column added.")
except Exception as e:
    print("Could not add term_name column:", e)

try:
    cursor.execute("ALTER TABLE guardians ADD COLUMN relationship TEXT")
    print("relationship column added to guardians.")
except Exception as e:
    print("Could not add relationship column:", e)

try:
    cursor.execute("ALTER TABLE guardians ADD COLUMN email TEXT")
    print("email column added to guardians.")
except Exception as e:
    print("Could not add email column:", e)

try:
    cursor.execute("ALTER TABLE students ADD COLUMN guardian2_name TEXT")
    print("guardian2_name column added to students.")
except Exception as e:
    print("Could not add guardian2_name column:", e)

try:
    cursor.execute("ALTER TABLE students ADD COLUMN guardian2_phone TEXT")
    print("guardian2_phone column added to students.")
except Exception as e:
    print("Could not add guardian2_phone column:", e)

conn.commit()
conn.close()
print("Done.")