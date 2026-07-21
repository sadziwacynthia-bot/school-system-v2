import sqlite3

conn = sqlite3.connect("school_v2.db")

count = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]

print("Attendance records:", count)

conn.close()