import sqlite3

conn = sqlite3.connect("school.db")
cursor = conn.cursor()

# Create guardians table
cursor.execute("""
CREATE TABLE IF NOT EXISTS guardians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    name TEXT,
    phone TEXT,
    relationship TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id)
)
""")

conn.commit()
conn.close()
print("Guardians table created successfully!")
