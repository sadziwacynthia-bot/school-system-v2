import sqlite3

conn = sqlite3.connect("school_v2.db")
conn.row_factory = sqlite3.Row

cursor = conn.cursor()

cursor.execute("PRAGMA table_info(cashbook)")

rows = cursor.fetchall()

print("Cashbook columns:")
print("-----------------")

for row in rows:
    print(row["name"])

conn.close()