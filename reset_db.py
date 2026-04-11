import sqlite3
from werkzeug.security import generate_password_hash
conn = sqlite3.connect("school.db")
cursor = conn.cursor()

# STUDENTS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_number TEXT UNIQUE,
    first_name TEXT,
    last_name TEXT,
    birthday TEXT,
    gender TEXT,
    enrollment_date TEXT,
    leaving_year TEXT,
    class_name TEXT,
    home_address TEXT,
    mailing_address TEXT,
    student_phone TEXT,
    medical_info TEXT,
    emergency_contact TEXT,
    guardian1_name TEXT,
    guardian1_relationship TEXT,
    guardian1_phone TEXT,
    guardian1_whatsapp TEXT,
    guardian1_email TEXT,
    guardian2_name TEXT,
    guardian2_relationship TEXT,
    guardian2_phone TEXT,
    guardian2_whatsapp TEXT,
    guardian2_email TEXT
)
""")

# FEES TABLE
# FEES TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS fees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    academic_year TEXT,

    term1_fee REAL DEFAULT 0,
    term1_paid REAL DEFAULT 0,
    term1_balance REAL DEFAULT 0,

    term2_fee REAL DEFAULT 0,
    term2_paid REAL DEFAULT 0,
    term2_balance REAL DEFAULT 0,

    term3_fee REAL DEFAULT 0,
    term3_paid REAL DEFAULT 0,
    term3_balance REAL DEFAULT 0,

    total_fee REAL DEFAULT 0,
    total_paid REAL DEFAULT 0,
    total_balance REAL DEFAULT 0,

    FOREIGN KEY (student_id) REFERENCES students(id)
)
""")

# ATTENDANCE TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    class_name TEXT,
    date TEXT,
    status TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id)
)
""")
# USERS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT,
    role TEXT NOT NULL,
    setup_code TEXT,
    must_set_password INTEGER DEFAULT 1
)
""")

# TEACHER CLASSES TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS teacher_classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    class_name TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")

# PARENT-STUDENT LINK TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS parent_students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    student_id INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (student_id) REFERENCES students(id)
)
""")
# TEACHERS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    teacher_id TEXT UNIQUE,
    full_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
# CLASSES TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT UNIQUE NOT NULL
)
""")
# CLASSES TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT UNIQUE NOT NULL
)
""")
# SUBJECTS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name TEXT UNIQUE NOT NULL
)
""")

# TEACHER SUBJECTS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS teacher_subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    class_name TEXT,
    subject_name TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
# ASSIGNMENTS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    class_name TEXT,
    subject_name TEXT,
    title TEXT,
    instructions TEXT,
    due_date TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
# RESULTS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    user_id INTEGER,
    class_name TEXT,
    subject_name TEXT,
    term TEXT,
    academic_year TEXT,
    mark REAL,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
default_subjects = [
    "Mathematics",
    "English",
    "Geography",
    "History",
    "Science",
    "Biology",
    "Chemistry",
    "Physics",
    "Accounting",
    "Religious Studies",
    "Shona",
    "Computer Science"
]

for subject_name in default_subjects:
    cursor.execute("""
        INSERT OR IGNORE INTO subjects (subject_name)
        VALUES (?)
    """, (subject_name,))

default_classes = [
    "Form 1 Blue",
    "Form 1 Grey",
    "Form 2 Blue",
    "Form 2 Grey",
    "Form 3 Blue",
    "Form 3 Grey",
    "Form 4 Blue",
    "Form 4 Grey",
    "Form 5",
    "Form 6"
]
cursor.execute("""
DELETE FROM classes
WHERE class_name NOT IN (
    'Form 1 Blue',
    'Form 1 Grey',
    'Form 2 Blue',
    'Form 2 Grey',
    'Form 3 Blue',
    'Form 3 Grey',
    'Form 4 Blue',
    'Form 4 Grey',
    'Form 5',
    'Form 6'
)
""")

for class_name in default_classes:
    cursor.execute("""
        INSERT OR IGNORE INTO classes (class_name)
        VALUES (?)
    """, (class_name,))
# DEFAULT DIRECTOR ACCOUNT
director_password = generate_password_hash("admin123")

cursor.execute("""
INSERT OR IGNORE INTO users (full_name, username, password, role, setup_code, must_set_password)
VALUES (?, ?, ?, ?, ?, ?)
""", ("System Director", "director", director_password, "director", "", 0))
conn.commit()
conn.close()

print("Database recreated successfully.")