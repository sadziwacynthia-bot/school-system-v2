from flask import session
from utils.db import get_db, is_postgres, execute_commit


def log_audit(action, table_name=None, record_id=None, details=None):
    try:
        execute_commit("""
            INSERT INTO audit_logs (
                school_id, user_id, username, role, action, table_name, record_id, details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get("school_id"),
            session.get("user_id"),
            session.get("username") or session.get("full_name"),
            session.get("role"),
            action,
            table_name,
            record_id,
            details
        ))
    except Exception as e:
        print("AUDIT LOG ERROR:", str(e), flush=True)


def run_audit_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER,
                    user_id INTEGER,
                    username VARCHAR(255),
                    role VARCHAR(50),
                    action TEXT,
                    table_name VARCHAR(100),
                    record_id INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS school_id INTEGER")
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS role VARCHAR(50)")

        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    role TEXT,
                    action TEXT,
                    table_name TEXT,
                    record_id INTEGER,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            for stmt in [
                "ALTER TABLE audit_logs ADD COLUMN school_id INTEGER",
                "ALTER TABLE audit_logs ADD COLUMN role TEXT"
            ]:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass

        conn.commit()
        print("Audit migration completed")

    except Exception as e:
        print("Audit migration error:", str(e))

    finally:
        conn.close()