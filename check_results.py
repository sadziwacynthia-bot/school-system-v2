import sqlite3

conn = sqlite3.connect("school_v2.db")
conn.row_factory = sqlite3.Row

cursor = conn.execute("PRAGMA table_info(results)")

for row in cursor.fetchall():
    print(dict(row))

conn.close()