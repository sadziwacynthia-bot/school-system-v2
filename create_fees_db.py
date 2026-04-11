import sqlite3

db = sqlite3.connect("school.db")
cursor = db.cursor()

# Create fees table
cursor.execute("""
CREATE TABLE IF NOT EXISTS fees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    amount REAL,
    status TEXT,
    due_date TEXT,
    FOREIGN KEY(student_id) REFERENCES students(id)
)
""")

db.commit()
db.close()

print("Fees table created successfully!")
