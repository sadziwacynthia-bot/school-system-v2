import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect("school.db")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
""")

cursor.execute("""
    INSERT OR IGNORE INTO users (full_name, username, password, role)
    VALUES (?, ?, ?, ?)
""", (
    "Administrator",
    "admin",
    generate_password_hash("admin123"),
    "admin"
))

conn.commit()
conn.close()

print("Admin user created.")