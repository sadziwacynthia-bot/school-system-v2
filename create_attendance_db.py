import sqlite3

db = sqlite3.connect("school.db")
cursor = db.cursor()

# Create attendance table
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    date TEXT,
    status TEXT,
    FOREIGN KEY(student_id) REFERENCES students(id)
)
""")

db.commit()
db.close()

print("Attendance table created successfully!")
