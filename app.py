from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import sqlite3
import random
import string
import urllib.parse
from functools import wraps
from datetime import datetime, date

import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "school-v2-secret-key"

CLASS_OPTIONS = [
    "Form 1 Grey", "Form 1 Blue",
    "Form 2 Grey", "Form 2 Blue",
    "Form 3 Grey", "Form 3 Blue",
    "Form 4 Grey", "Form 4 Blue",
    "Form 5", "Form 6"
]

DB_PATH = os.path.join(os.path.dirname(__file__), "school_v2.db")


# =========================================================
# DATABASE HELPERS
# =========================================================
def is_postgres():
    return os.environ.get("DATABASE_URL") is not None


def get_db():
    if is_postgres():
        return psycopg2.connect(
            os.environ.get("DATABASE_URL"),
            cursor_factory=RealDictCursor
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def convert_query(query: str) -> str:
    if is_postgres():
        return query.replace("?", "%s")
    return query


def fetch_one(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(convert_query(query), params)
    row = cursor.fetchone()
    conn.close()
    return row


def fetch_all(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(convert_query(query), params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def execute_commit(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(convert_query(query), params)
    conn.commit()
    conn.close()


def insert_and_get_id(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute(convert_query(query + " RETURNING id"), params)
            row = cursor.fetchone()
            new_id = row["id"]
        else:
            cursor.execute(convert_query(query), params)
            new_id = cursor.lastrowid
        conn.commit()
        return new_id
    finally:
        conn.close()


# =========================================================
# DATABASE SETUP
# =========================================================
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schools (
                id SERIAL PRIMARY KEY,
                school_name VARCHAR(255) NOT NULL,
                school_code VARCHAR(100) UNIQUE NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                full_name VARCHAR(255) NOT NULL,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                student_number VARCHAR(100) UNIQUE,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                birthday VARCHAR(50),
                gender VARCHAR(20),
                enrollment_date VARCHAR(50),
                leaving_year VARCHAR(20),
                class_name VARCHAR(100),
                boarding_status VARCHAR(30),
                home_address TEXT,
                mailing_address TEXT,
                student_phone VARCHAR(50),
                medical_info TEXT,
                emergency_contact VARCHAR(100),
                guardian1_name VARCHAR(255),
                guardian1_relationship VARCHAR(100),
                guardian1_phone VARCHAR(50),
                guardian1_whatsapp VARCHAR(50),
                guardian1_email VARCHAR(255),
                guardian2_name VARCHAR(255),
                guardian2_relationship VARCHAR(100),
                guardian2_phone VARCHAR(50),
                guardian2_whatsapp VARCHAR(50),
                guardian2_email VARCHAR(255),
                current_status VARCHAR(50)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                user_id INTEGER,
                teacher_id VARCHAR(50),
                full_name VARCHAR(255),
                phone VARCHAR(50),
                email VARCHAR(255)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guardians (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                student_id INTEGER,
                parent_user_id INTEGER,
                full_name VARCHAR(255),
                relationship VARCHAR(100),
                phone VARCHAR(50),
                whatsapp VARCHAR(50),
                email VARCHAR(255)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fees (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                student_id INTEGER,
                term_name VARCHAR(50),
                amount NUMERIC(10,2),
                paid_amount NUMERIC(10,2) DEFAULT 0,
                balance NUMERIC(10,2),
                status VARCHAR(50),
                due_date VARCHAR(50)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                student_id INTEGER,
                class_name VARCHAR(100),
                subject VARCHAR(100),
                term VARCHAR(50),
                marks NUMERIC(10,2),
                grade VARCHAR(10)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                student_id INTEGER,
                class_name VARCHAR(100),
                date VARCHAR(50),
                status VARCHAR(50)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teacher_assignments (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                teacher_id INTEGER,
                class_name VARCHAR(100),
                subject VARCHAR(100)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assignments (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                class_name VARCHAR(100),
                subject VARCHAR(100),
                title VARCHAR(255),
                description TEXT,
                due_date VARCHAR(50),
                created_by VARCHAR(255)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fee_payments (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                fee_id INTEGER,
                payment_date VARCHAR(50),
                amount_paid NUMERIC(10,2),
                receipt_number VARCHAR(100)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timetables (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                class_name VARCHAR(100),
                subject VARCHAR(100),
                teacher_id INTEGER,
                day_of_week VARCHAR(20),
                start_time VARCHAR(20),
                end_time VARCHAR(20),
                room VARCHAR(100)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id SERIAL PRIMARY KEY,
                school_id INTEGER,
                subject_name VARCHAR(100) NOT NULL,
                weekly_periods INTEGER DEFAULT 1,
                preferred_session VARCHAR(20) DEFAULT 'any',
                is_practical INTEGER DEFAULT 0,
                requires_double_period INTEGER DEFAULT 0,
                requires_four_block INTEGER DEFAULT 0,
                requires_two_block INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timetable_settings (
                id SERIAL PRIMARY KEY,
                school_id INTEGER UNIQUE,
                start_time VARCHAR(20),
                period_length INTEGER DEFAULT 35,
                periods_per_day INTEGER DEFAULT 8,
                break_after_period INTEGER DEFAULT 3,
                break_duration INTEGER DEFAULT 20,
                lunch_after_period INTEGER DEFAULT 5,
                lunch_duration INTEGER DEFAULT 40
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_name TEXT NOT NULL,
                school_code TEXT UNIQUE NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                full_name TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                student_number TEXT UNIQUE,
                first_name TEXT,
                last_name TEXT,
                birthday TEXT,
                gender TEXT,
                enrollment_date TEXT,
                leaving_year TEXT,
                class_name TEXT,
                boarding_status TEXT,
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
                guardian2_email TEXT,
                current_status TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                user_id INTEGER,
                teacher_id TEXT,
                full_name TEXT,
                phone TEXT,
                email TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guardians (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                student_id INTEGER,
                parent_user_id INTEGER,
                full_name TEXT,
                relationship TEXT,
                phone TEXT,
                whatsapp TEXT,
                email TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                student_id INTEGER,
                term_name TEXT,
                amount REAL,
                paid_amount REAL DEFAULT 0,
                balance REAL,
                status TEXT,
                due_date TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                student_id INTEGER,
                class_name TEXT,
                subject TEXT,
                term TEXT,
                marks REAL,
                grade TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                student_id INTEGER,
                class_name TEXT,
                date TEXT,
                status TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teacher_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                teacher_id INTEGER,
                class_name TEXT,
                subject TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                class_name TEXT,
                subject TEXT,
                title TEXT,
                description TEXT,
                due_date TEXT,
                created_by TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fee_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                fee_id INTEGER,
                payment_date TEXT,
                amount_paid REAL,
                receipt_number TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timetables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                class_name TEXT,
                subject TEXT,
                teacher_id INTEGER,
                day_of_week TEXT,
                start_time TEXT,
                end_time TEXT,
                room TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER,
                subject_name TEXT NOT NULL,
                weekly_periods INTEGER DEFAULT 1,
                preferred_session TEXT DEFAULT 'any',
                is_practical INTEGER DEFAULT 0,
                requires_double_period INTEGER DEFAULT 0,
                requires_four_block INTEGER DEFAULT 0,
                requires_two_block INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timetable_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER UNIQUE,
                start_time TEXT,
                period_length INTEGER DEFAULT 35,
                periods_per_day INTEGER DEFAULT 8,
                break_after_period INTEGER DEFAULT 3,
                break_duration INTEGER DEFAULT 20,
                lunch_after_period INTEGER DEFAULT 5,
                lunch_duration INTEGER DEFAULT 40
            )
        """)
    conn.commit()
    conn.close()


def run_migrations():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            statements = [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE students ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE teachers ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE guardians ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE fees ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE results ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE teacher_assignments ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE fee_payments ADD COLUMN IF NOT EXISTS school_id INTEGER",
            ]
            for stmt in statements:
                cursor.execute(stmt)
        else:
            sqlite_statements = [
                "ALTER TABLE users ADD COLUMN school_id INTEGER",
                "ALTER TABLE students ADD COLUMN school_id INTEGER",
                "ALTER TABLE teachers ADD COLUMN school_id INTEGER",
                "ALTER TABLE guardians ADD COLUMN school_id INTEGER",
                "ALTER TABLE fees ADD COLUMN school_id INTEGER",
                "ALTER TABLE results ADD COLUMN school_id INTEGER",
                "ALTER TABLE attendance ADD COLUMN school_id INTEGER",
                "ALTER TABLE teacher_assignments ADD COLUMN school_id INTEGER",
                "ALTER TABLE assignments ADD COLUMN school_id INTEGER",
                "ALTER TABLE fee_payments ADD COLUMN school_id INTEGER",
            ]
            for stmt in sqlite_statements:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass
        conn.commit()
    finally:
        conn.close()


def create_default_school():
    school = fetch_one("SELECT * FROM schools WHERE school_code = ?", ("SCH001",))
    if not school:
        execute_commit(
            "INSERT INTO schools (school_name, school_code) VALUES (?, ?)",
            ("My School", "SCH001"),
        )


def assign_existing_data_to_default_school():
    school = fetch_one("SELECT * FROM schools WHERE school_code = ?", ("SCH001",))
    if not school:
        return
    school_id = school["id"]

    execute_commit("UPDATE users SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE students SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE teachers SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE guardians SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE fees SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE results SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE attendance SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE teacher_assignments SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE assignments SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE fee_payments SET school_id = ? WHERE school_id IS NULL", (school_id,))


def migrate_roles():
    execute_commit(
        "UPDATE users SET role = ? WHERE role IN ('admin', 'director')",
        ("school_admin",)
    )


def create_super_admin():
    school = fetch_one("SELECT * FROM schools WHERE school_code = ?", ("SCH001",))
    admin = fetch_one("SELECT * FROM users WHERE username = ?", ("superadmin",))
    if not admin and school:
        execute_commit(
            """
            INSERT INTO users (school_id, full_name, username, password, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                school["id"],
                "Super Admin",
                "superadmin",
                generate_password_hash("admin123"),
                "super_admin",
            ),
        )


# =========================================================
# HELPERS
# =========================================================
def generate_student_number():
    return "STU" + "".join(random.choices(string.ascii_uppercase, k=2)) + "".join(random.choices(string.digits, k=4))


def generate_teacher_id():
    return "TCH" + "".join(random.choices(string.digits, k=3))


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        school_id = session.get("school_id")
        role = session.get("role")

        if role != "super_admin" and school_id:
            school = fetch_one("SELECT * FROM schools WHERE id = ?", (school_id,))
            if school:
                is_active = row_get(school, "is_active", 1)
                subscription_status = row_get(school, "subscription_status", "active")

                if int(is_active or 0) != 1 or subscription_status in ["suspended", "overdue"]:
                    session.clear()
                    return redirect(url_for("subscription_expired"))

        return f(*args, **kwargs)
    return wrapper

def roles_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))

            role = session.get("role")
            if role not in allowed_roles:
                flash("You are not allowed to access that page.", "danger")
                if role == "parent":
                    return redirect(url_for("parent_dashboard"))
                if role == "teacher":
                    return redirect(url_for("teacher_dashboard"))
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def delete_by_scope(cursor, query, params):
    cursor.execute(convert_query(query), params)


def row_get(row, key, default=None):
    try:
        if row is None:
            return default
        if isinstance(row, dict):
            return row.get(key, default)
        if hasattr(row, "keys") and key not in row.keys():
            return default
        return row[key]
    except Exception:
        return default


def parse_date_safe(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str), "%Y-%m-%d").date()
    except Exception:
        return None


def get_school_settings(school_id):
    if not school_id:
        return None

    try:
        settings = fetch_one(
            "SELECT * FROM school_settings WHERE school_id = ?",
            (school_id,)
        )
        if settings:
            return settings
    except Exception:
        pass

    school = fetch_one("SELECT * FROM schools WHERE id = ?", (school_id,))
    if not school:
        return None

    return {
        "school_id": school_id,
        "display_name": row_get(school, "school_name", "EduTrack"),
        "phone": "",
        "email": "",
        "address": "",
        "report_header": "School Management System",
        "logo_url": "",
    }


def school_is_overdue(school):
    end_date = parse_date_safe(row_get(school, "subscription_end_date"))
    if not end_date:
        return False
    return end_date < datetime.now().date()


def cashbook_insert_income(cursor, school_id, payment_date, amount_paid, receipt_number, student_name, term_name, created_by):
    try:
        amount = float(amount_paid or 0)
    except Exception:
        amount = 0

    if amount <= 0:
        return

    entry_date = payment_date or datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        convert_query("""
            INSERT INTO cashbook (
                school_id, entry_date, entry_type, category, description,
                amount, payment_method, reference_number, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """),
        (
            school_id,
            entry_date,
            "income",
            "School Fees",
            f"Fee payment from {student_name} for {term_name}",
            amount,
            "School Fee Payment",
            receipt_number,
            created_by,
        )
    )
def get_school_classes(school_id):
    rows = fetch_all(
        "SELECT * FROM school_classes WHERE school_id = ? ORDER BY class_name",
        (school_id,)
    )

    if rows:
        return [row["class_name"] for row in rows]

    return CLASS_OPTIONS


# =========================================================
# BASIC ROUTES
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = fetch_one("SELECT * FROM users WHERE username = ?", (username,))
        if user and int(row_get(user, "is_active", 1) or 1) != 1:
            flash("This account has been deactivated. Please contact the school administrator.", "danger")
            return redirect(url_for("login"))
        
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["school_id"] = user["school_id"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]

            if user["role"] == "parent":
                return redirect(url_for("parent_dashboard"))
            elif user["role"] == "teacher":
                return redirect(url_for("teacher_dashboard"))
            else:
                return redirect(url_for("dashboard"))

        flash("Invalid login details.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
@roles_required("school_admin", "super_admin")
def dashboard():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        total_schools = fetch_one("SELECT COUNT(*) AS total FROM schools")["total"]
        total_students = fetch_one("SELECT COUNT(*) AS total FROM students")["total"]
        total_teachers = fetch_one("SELECT COUNT(*) AS total FROM teachers")["total"]
        total_users = fetch_one("SELECT COUNT(*) AS total FROM users")["total"]
        total_fee_records = fetch_one("SELECT COUNT(*) AS total FROM fees")["total"]

        fee_totals = fetch_one("""
            SELECT
                COALESCE(SUM(amount), 0) AS total_billed,
                COALESCE(SUM(paid_amount), 0) AS total_paid,
                COALESCE(SUM(balance), 0) AS total_balance
            FROM fees
        """)

        paid_count = fetch_one("SELECT COUNT(*) AS total FROM fees WHERE status = ?", ("Paid",))["total"]
        partial_count = fetch_one("SELECT COUNT(*) AS total FROM fees WHERE status = ?", ("Partially Paid",))["total"]
        pending_count = fetch_one("SELECT COUNT(*) AS total FROM fees WHERE status = ?", ("Pending",))["total"]

    else:
        total_schools = 0
        total_students = fetch_one("SELECT COUNT(*) AS total FROM students WHERE school_id = ?", (school_id,))["total"]
        total_teachers = fetch_one("SELECT COUNT(*) AS total FROM teachers WHERE school_id = ?", (school_id,))["total"]
        total_users = fetch_one("SELECT COUNT(*) AS total FROM users WHERE school_id = ?", (school_id,))["total"]
        total_fee_records = fetch_one("SELECT COUNT(*) AS total FROM fees WHERE school_id = ?", (school_id,))["total"]

        fee_totals = fetch_one("""
            SELECT
                COALESCE(SUM(amount), 0) AS total_billed,
                COALESCE(SUM(paid_amount), 0) AS total_paid,
                COALESCE(SUM(balance), 0) AS total_balance
            FROM fees
            WHERE school_id = ?
        """, (school_id,))

        paid_count = fetch_one("SELECT COUNT(*) AS total FROM fees WHERE school_id = ? AND status = ?", (school_id, "Paid"))["total"]
        partial_count = fetch_one("SELECT COUNT(*) AS total FROM fees WHERE school_id = ? AND status = ?", (school_id, "Partially Paid"))["total"]
        pending_count = fetch_one("SELECT COUNT(*) AS total FROM fees WHERE school_id = ? AND status = ?", (school_id, "Pending"))["total"]

    return render_template(
        "dashboard.html",
        total_schools=total_schools,
        total_students=total_students,
        total_teachers=total_teachers,
        total_users=total_users,
        total_fee_records=total_fee_records,
        total_billed=fee_totals["total_billed"] or 0,
        total_paid=fee_totals["total_paid"] or 0,
        total_balance=fee_totals["total_balance"] or 0,
        paid_count=paid_count,
        partial_count=partial_count,
        pending_count=pending_count
    )

# =========================================================
# SCHOOL ADMINISTRATION
# =========================================================
@app.route("/schools")
@login_required
@roles_required("super_admin")
def schools():
    school_rows = fetch_all("SELECT * FROM schools ORDER BY school_name")
    schools_data = []

    for school in school_rows:
        schools_data.append({
            "id": school["id"],
            "school_name": school["school_name"],
            "school_code": school["school_code"],
            "is_active": row_get(school, "is_active", 1),
            "subscription_status": row_get(school, "subscription_status", "active"),
            "subscription_end_date": row_get(school, "subscription_end_date"),
        })

    return render_template("schools.html", schools=schools_data)

@app.route("/add_school", methods=["GET", "POST"])
@login_required
@roles_required("super_admin")
def add_school():
    if request.method == "POST":
        school_name = request.form.get("school_name", "").strip()
        school_code = request.form.get("school_code", "").strip()

        if not school_name or not school_code:
            flash("School name and school code are required.", "danger")
            return redirect(url_for("add_school"))

        existing = fetch_one("SELECT * FROM schools WHERE school_code = ?", (school_code,))
        if existing:
            flash("School code already exists.", "danger")
            return redirect(url_for("add_school"))

        try:
            execute_commit(
                """
                INSERT INTO schools (school_name, school_code, is_active, subscription_status)
                VALUES (?, ?, ?, ?)
                """,
                (school_name, school_code, 1, "active")
            )
        except Exception:
            execute_commit(
                "INSERT INTO schools (school_name, school_code) VALUES (?, ?)",
                (school_name, school_code)
            )

        flash("School created successfully.", "success")
        return redirect(url_for("schools"))

    return render_template("add_school.html")

@app.route("/add_school_admin", methods=["GET", "POST"])
@login_required
@roles_required("super_admin")
def add_school_admin():
    school_list = fetch_all("SELECT * FROM schools ORDER BY school_name")

    if request.method == "POST":
        school_id = request.form.get("school_id")
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not school_id or not full_name or not username or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("add_school_admin"))

        existing = fetch_one("SELECT * FROM users WHERE username = ?", (username,))
        if existing:
            flash("Username already exists.", "danger")
            return redirect(url_for("add_school_admin"))

        execute_commit(
            """
            INSERT INTO users (school_id, full_name, username, password, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (school_id, full_name, username, generate_password_hash(password), "school_admin"),
        )
        flash("School admin created successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_school_admin.html", schools=school_list)

@app.route("/audit_logs")
@login_required
@roles_required("super_admin", "school_admin")
def audit_logs():
    logs = fetch_all("""
        SELECT *
        FROM audit_logs
        ORDER BY created_at DESC
        LIMIT 200
    """)

    return render_template("audit_logs.html", logs=logs)


@app.route("/fix_audit_table")
@login_required
@roles_required("super_admin", "school_admin")
def fix_audit_table():
    run_audit_migration()
    return "Audit table created successfully."

# =========================================================
# STUDENTS
# =========================================================

@app.route("/students")
@login_required
@roles_required("super_admin", "school_admin", "teacher")
def students():
    search = request.args.get("search", "").strip()
    school_id = session.get("school_id")
    role = session.get("role")

    params = []
    query = """
        SELECT *,
               COALESCE(current_status, 'Active') AS status
        FROM students
        WHERE 1=1
    """

    if role != "super_admin":
        query += " AND school_id = ?"
        params.append(school_id)

    if search:
        query += """
            AND (
                first_name LIKE ?
                OR last_name LIKE ?
                OR student_number LIKE ?
                OR class_name LIKE ?
            )
        """
        like = f"%{search}%"
        params.extend([like, like, like, like])

    query += " ORDER BY class_name, last_name, first_name"

    students = fetch_all(query, tuple(params))
    return render_template("students.html", students=students, search=search)



@app.route("/add_student")
@login_required
@roles_required("school_admin", "super_admin")
def add_student():
    schools = fetch_all("SELECT * FROM schools ORDER BY school_name")
    return render_template("add_student.html", class_options=CLASS_OPTIONS, schools=schools)


@app.route("/save_student", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def save_student():
    if session.get("role") == "super_admin":
        school_id = request.form.get("school_id")
    else:
        school_id = session.get("school_id")

    if not school_id:
        flash("Please select a school.", "danger")
        return redirect(url_for("add_student"))

    first_name = request.form.get("first_name")
    last_name = request.form.get("last_name")
    birthday = request.form.get("birthday")
    gender = request.form.get("gender")
    enrollment_date = request.form.get("enrollment_date")
    leaving_year = request.form.get("leaving_year")
    class_name = request.form.get("class_name")
    boarding_status = request.form.get("boarding_status")
    home_address = request.form.get("home_address")
    mailing_address = request.form.get("mailing_address")
    student_phone = request.form.get("student_phone")
    medical_info = request.form.get("medical_info")
    emergency_contact = request.form.get("emergency_contact")
    guardian1_name = request.form.get("guardian1_name")
    guardian1_relationship = request.form.get("guardian1_relationship")
    guardian1_phone = request.form.get("guardian1_phone")
    guardian1_whatsapp = request.form.get("guardian1_whatsapp")
    guardian1_email = request.form.get("guardian1_email")
    guardian2_name = request.form.get("guardian2_name")
    guardian2_relationship = request.form.get("guardian2_relationship")
    guardian2_phone = request.form.get("guardian2_phone")
    guardian2_whatsapp = request.form.get("guardian2_whatsapp")
    guardian2_email = request.form.get("guardian2_email")
    current_status = request.form.get("current_status") or "Active"
    parent_username = (request.form.get("parent_username") or guardian1_phone or "").strip()

    if not first_name or not last_name or not class_name:
        flash("First name, last name, and class are required.", "danger")
        return redirect(url_for("add_student"))

    student_number = generate_student_number()
    temporary_password = "".join(random.choices(string.ascii_letters + string.digits, k=8))

    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute(
                convert_query("""
                    INSERT INTO students (
                        school_id, student_number, first_name, last_name, birthday, gender,
                        enrollment_date, leaving_year, class_name, boarding_status,
                        home_address, mailing_address, student_phone, medical_info,
                        emergency_contact, guardian1_name, guardian1_relationship,
                        guardian1_phone, guardian1_whatsapp, guardian1_email,
                        guardian2_name, guardian2_relationship, guardian2_phone,
                        guardian2_whatsapp, guardian2_email, current_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING id
                """),
                (
                    school_id, student_number, first_name, last_name, birthday, gender,
                    enrollment_date, leaving_year, class_name, boarding_status,
                    home_address, mailing_address, student_phone, medical_info,
                    emergency_contact, guardian1_name, guardian1_relationship,
                    guardian1_phone, guardian1_whatsapp, guardian1_email,
                    guardian2_name, guardian2_relationship, guardian2_phone,
                    guardian2_whatsapp, guardian2_email, current_status
                )
            )
            student_id = cursor.fetchone()["id"]
        else:
            cursor.execute("""
                INSERT INTO students (
                    school_id, student_number, first_name, last_name, birthday, gender,
                    enrollment_date, leaving_year, class_name, boarding_status,
                    home_address, mailing_address, student_phone, medical_info,
                    emergency_contact, guardian1_name, guardian1_relationship,
                    guardian1_phone, guardian1_whatsapp, guardian1_email,
                    guardian2_name, guardian2_relationship, guardian2_phone,
                    guardian2_whatsapp, guardian2_email, current_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                school_id, student_number, first_name, last_name, birthday, gender,
                enrollment_date, leaving_year, class_name, boarding_status,
                home_address, mailing_address, student_phone, medical_info,
                emergency_contact, guardian1_name, guardian1_relationship,
                guardian1_phone, guardian1_whatsapp, guardian1_email,
                guardian2_name, guardian2_relationship, guardian2_phone,
                guardian2_whatsapp, guardian2_email, current_status
            ))
            student_id = cursor.lastrowid

        parent_user_id = None
        if parent_username:
            existing_parent = fetch_one("SELECT * FROM users WHERE username = ?", (parent_username,))
            if existing_parent:
                parent_user_id = existing_parent["id"]
            else:
                if is_postgres():
                    cursor.execute(
                        convert_query("""
                            INSERT INTO users (school_id, full_name, username, password, role)
                            VALUES (?, ?, ?, ?, ?)
                            RETURNING id
                        """),
                        (
                            school_id,
                            guardian1_name or f"{first_name} Parent",
                            parent_username,
                            generate_password_hash(temporary_password),
                            "parent",
                        ),
                    )
                    parent_user_id = cursor.fetchone()["id"]
                else:
                    cursor.execute("""
                        INSERT INTO users (school_id, full_name, username, password, role)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        school_id,
                        guardian1_name or f"{first_name} Parent",
                        parent_username,
                        generate_password_hash(temporary_password),
                        "parent",
                    ))
                    parent_user_id = cursor.lastrowid

        if guardian1_name or guardian1_phone:
            cursor.execute(
                convert_query("""
                    INSERT INTO guardians (
                        school_id, student_id, parent_user_id, full_name, relationship, phone, whatsapp, email
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """),
                (
                    school_id, student_id, parent_user_id, guardian1_name,
                    guardian1_relationship, guardian1_phone, guardian1_whatsapp, guardian1_email
                ),
            )

        if guardian2_name or guardian2_phone:
            cursor.execute(
                convert_query("""
                    INSERT INTO guardians (
                        school_id, student_id, parent_user_id, full_name, relationship, phone, whatsapp, email
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """),
                (
                    school_id, student_id, parent_user_id, guardian2_name,
                    guardian2_relationship, guardian2_phone, guardian2_whatsapp, guardian2_email
                ),
            )
        try:
            cursor.execute(
                convert_query("""
                    INSERT INTO school_classes (school_id, class_name)
                    VALUES (?, ?)
                """),
                (school_id, class_name)
            )
        except Exception:
            pass
        conn.commit()

        log_audit(
    "Added student",
    "students",
    student_id,
    f"Added {first_name} {last_name} - {student_number}"
)

        if parent_username and parent_user_id:
            flash(
                f"Student added successfully. Student Number: {student_number}. Parent username: {parent_username}. Temporary password: {temporary_password}",
                "success",
            )
        else:
            flash(f"Student added successfully. Student Number: {student_number}", "success")

        return redirect(url_for("students"))

    except Exception as e:
        conn.rollback()
        flash(f"Error saving student: {str(e)}", "danger")
        return redirect(url_for("add_student"))

    finally:
        conn.close()



@app.route("/student_profile/<int:id>")
@login_required
def student_profile(id):
    student = fetch_one("""
        SELECT *,
               COALESCE(current_status, 'Active') AS status
        FROM students
        WHERE id = ?
    """, (id,))

    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("students"))

    return render_template("student_profile.html", student=student)



@app.route("/edit_student/<int:id>")
@login_required
@roles_required("school_admin", "super_admin")
def edit_student(id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (id,))
    else:
        student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (id, school_id))

    if not student:
        flash("Student not found or access denied.", "danger")
        return redirect(url_for("students"))

    return render_template("edit_student.html", student=student, class_options=CLASS_OPTIONS)


@app.route("/update_student/<int:id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def update_student(id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (id,))
    else:
        student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (id, school_id))

    if not student:
        flash("Student not found or access denied.", "danger")
        return redirect(url_for("students"))

    execute_commit(
        """
        UPDATE students
        SET
            first_name = ?,
            last_name = ?,
            birthday = ?,
            gender = ?,
            enrollment_date = ?,
            leaving_year = ?,
            class_name = ?,
            boarding_status = ?,
            home_address = ?,
            mailing_address = ?,
            student_phone = ?,
            medical_info = ?,
            emergency_contact = ?,
            guardian1_name = ?,
            guardian1_relationship = ?,
            guardian1_phone = ?,
            guardian1_whatsapp = ?,
            guardian1_email = ?,
            guardian2_name = ?,
            guardian2_relationship = ?,
            guardian2_phone = ?,
            guardian2_whatsapp = ?,
            guardian2_email = ?,
            current_status = ?
        WHERE id = ?
        """,
        (
            request.form.get("first_name"),
            request.form.get("last_name"),
            request.form.get("birthday"),
            request.form.get("gender"),
            request.form.get("enrollment_date"),
            request.form.get("leaving_year"),
            request.form.get("class_name"),
            request.form.get("boarding_status"),
            request.form.get("home_address"),
            request.form.get("mailing_address"),
            request.form.get("student_phone"),
            request.form.get("medical_info"),
            request.form.get("emergency_contact"),
            request.form.get("guardian1_name"),
            request.form.get("guardian1_relationship"),
            request.form.get("guardian1_phone"),
            request.form.get("guardian1_whatsapp"),
            request.form.get("guardian1_email"),
            request.form.get("guardian2_name"),
            request.form.get("guardian2_relationship"),
            request.form.get("guardian2_phone"),
            request.form.get("guardian2_whatsapp"),
            request.form.get("guardian2_email"),
            request.form.get("current_status"),
            id,
        ),
    )
    log_audit(
    "Updated student",
    "students",
    id,
    f"Updated student ID {id}"
)

    flash("Student updated successfully.", "success")
    return redirect(url_for("student_profile", id=id))


@app.route("/delete_student/<int:id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def delete_student(id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (id,))
    else:
        student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (id, school_id))

    if not student:
        flash("Student not found or access denied.", "danger")
        return redirect(url_for("students"))

    conn = get_db()
    cursor = conn.cursor()

    try:
        if role == "super_admin":
            delete_by_scope(cursor, "DELETE FROM guardians WHERE student_id = ?", (id,))
            delete_by_scope(cursor, "DELETE FROM fees WHERE student_id = ?", (id,))
            delete_by_scope(cursor, "DELETE FROM results WHERE student_id = ?", (id,))
            delete_by_scope(cursor, "DELETE FROM attendance WHERE student_id = ?", (id,))
            delete_by_scope(cursor, "DELETE FROM students WHERE id = ?", (id,))
        else:
            delete_by_scope(cursor, "DELETE FROM guardians WHERE student_id = ? AND school_id = ?", (id, school_id))
            delete_by_scope(cursor, "DELETE FROM fees WHERE student_id = ? AND school_id = ?", (id, school_id))
            delete_by_scope(cursor, "DELETE FROM results WHERE student_id = ? AND school_id = ?", (id, school_id))
            delete_by_scope(cursor, "DELETE FROM attendance WHERE student_id = ? AND school_id = ?", (id, school_id))
            delete_by_scope(cursor, "DELETE FROM students WHERE id = ? AND school_id = ?", (id, school_id))

        conn.commit()
        flash("Student deleted successfully.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting student: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("students"))



@app.route("/student/activate/<int:id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def activate_student(id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (id,))
    else:
        student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (id, school_id))

    if not student:
        flash("Student not found or access denied.", "danger")
        return redirect(url_for("students"))

    execute_commit("UPDATE students SET current_status = ? WHERE id = ?", ("Active", id))
    flash("Student activated successfully.", "success")
    return redirect(url_for("students"))


# =========================================================
# TEACHERS
# =========================================================
@app.route("/teachers")
@login_required
@roles_required("school_admin", "super_admin")
def teachers():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        teacher_list = fetch_all("SELECT * FROM teachers ORDER BY full_name")
    else:
        teacher_list = fetch_all("SELECT * FROM teachers WHERE school_id = ? ORDER BY full_name", (school_id,))

    return render_template("teachers.html", teachers=teacher_list)


@app.route("/teacher_registration", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def teacher_registration():
    school_id = session.get("school_id")

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not full_name or not username or not password:
            flash("Full name, username, and password are required.", "danger")
            return redirect(url_for("teacher_registration"))

        existing_user = fetch_one("SELECT * FROM users WHERE username = ?", (username,))
        if existing_user:
            flash("Username already exists.", "danger")
            return redirect(url_for("teacher_registration"))

        conn = get_db()
        cursor = conn.cursor()

        try:
            if is_postgres():
                cursor.execute(
                    convert_query("""
                        INSERT INTO users (school_id, full_name, username, password, role)
                        VALUES (?, ?, ?, ?, ?)
                        RETURNING id
                    """),
                    (school_id, full_name, username, generate_password_hash(password), "teacher"),
                )
                user_id = cursor.fetchone()["id"]
            else:
                cursor.execute("""
                    INSERT INTO users (school_id, full_name, username, password, role)
                    VALUES (?, ?, ?, ?, ?)
                """, (school_id, full_name, username, generate_password_hash(password), "teacher"))
                user_id = cursor.lastrowid

            cursor.execute(
                convert_query("""
                    INSERT INTO teachers (school_id, user_id, teacher_id, full_name, phone, email)
                    VALUES (?, ?, ?, ?, ?, ?)
                """),
                (school_id, user_id, generate_teacher_id(), full_name, phone, email),
            )

            conn.commit()
            flash("Teacher registered successfully.", "success")
            return redirect(url_for("teachers"))
        except Exception as e:
            conn.rollback()
            flash(f"Error registering teacher: {str(e)}", "danger")
            return redirect(url_for("teacher_registration"))
        finally:
            conn.close()

    return render_template("teacher_registration.html")


@app.route("/assign_teacher", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def assign_teacher():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        teachers_list = fetch_all("SELECT * FROM teachers ORDER BY full_name")
        assignments_list = fetch_all("""
            SELECT ta.*, t.full_name
            FROM teacher_assignments ta
            JOIN teachers t ON ta.teacher_id = t.id
            ORDER BY t.full_name, ta.class_name, ta.subject
        """)
    else:
        teachers_list = fetch_all("SELECT * FROM teachers WHERE school_id = ? ORDER BY full_name", (school_id,))
        assignments_list = fetch_all("""
            SELECT ta.*, t.full_name
            FROM teacher_assignments ta
            JOIN teachers t ON ta.teacher_id = t.id
            WHERE ta.school_id = ?
            ORDER BY t.full_name, ta.class_name, ta.subject
        """, (school_id,))

    subjects_list = ["Math", "English", "Science", "History", "Geography", "Biology"]

    if request.method == "POST":
        teacher_id = request.form.get("teacher_id")
        class_name = request.form.get("class_name")
        subject = request.form.get("subject")

        if not teacher_id or not class_name or not subject:
            flash("Teacher, class, and subject are required.", "danger")
            return redirect(url_for("assign_teacher"))

        if role != "super_admin":
            teacher = fetch_one("SELECT * FROM teachers WHERE id = ? AND school_id = ?", (teacher_id, school_id))
            if not teacher:
                flash("Invalid teacher selected.", "danger")
                return redirect(url_for("assign_teacher"))

        execute_commit(
            """
            INSERT INTO teacher_assignments (school_id, teacher_id, class_name, subject)
            VALUES (?, ?, ?, ?)
            """,
            (school_id, teacher_id, class_name, subject),
        )

        flash("Teacher assigned successfully.", "success")
        return redirect(url_for("assign_teacher"))

    return render_template(
        "assign_teacher.html",
        teachers=teachers_list,
        class_options=CLASS_OPTIONS,
        subjects=subjects_list,
        assignments=assignments_list,
    )


@app.route("/teacher_dashboard")
@login_required
@roles_required("teacher")
def teacher_dashboard():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    teacher = fetch_one("""
        SELECT * FROM teachers
        WHERE user_id = ? AND school_id = ?
        LIMIT 1
    """, (user_id, school_id))

    assignments_list = []
    timetable_rows = []
    assigned_classes = []
    assigned_subjects = []

    if teacher:
        assignments_list = fetch_all("""
            SELECT *
            FROM teacher_assignments
            WHERE teacher_id = ? AND school_id = ?
            ORDER BY class_name, subject
        """, (teacher["id"], school_id))

        timetable_rows = fetch_all("""
            SELECT *
            FROM timetables
            WHERE teacher_id = ? AND school_id = ?
            ORDER BY day_of_week, start_time
        """, (teacher["id"], school_id))

        assigned_classes = sorted(list(set([a["class_name"] for a in assignments_list])))
        assigned_subjects = sorted(list(set([a["subject"] for a in assignments_list])))

    return render_template(
        "teacher_dashboard.html",
        teacher=teacher,
        assignments=assignments_list,
        timetable_rows=timetable_rows,
        assigned_classes=assigned_classes,
        assigned_subjects=assigned_subjects
    )

# =========================================================
# FEES
# =========================================================
@app.route("/fees")
@login_required
@roles_required("school_admin", "super_admin")
def fees():
    school_id = session.get("school_id")
    role = session.get("role")
    search = request.args.get("search", "").strip()

    params = []
    query = """
        SELECT f.*, s.first_name, s.last_name, s.student_number, s.class_name
        FROM fees f
        JOIN students s ON f.student_id = s.id
    """
    conditions = []

    if role != "super_admin":
        conditions.append("f.school_id = ?")
        params.append(school_id)

    if search:
        conditions.append("(s.first_name LIKE ? OR s.last_name LIKE ? OR s.student_number LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY s.class_name, s.first_name, s.last_name, f.term_name"
    fee_records = fetch_all(query, tuple(params))
    return render_template("fees.html", fee_records=fee_records, search=search)


@app.route("/add_fee", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def add_fee():
    school_id = session.get("school_id")
    role = session.get("role")

    selected_class = request.args.get("class_name", "").strip()

    if role == "super_admin":
        students = fetch_all(
            "SELECT * FROM students WHERE class_name = ? ORDER BY first_name, last_name",
            (selected_class,)
        ) if selected_class else []
    else:
        students = fetch_all(
            "SELECT * FROM students WHERE school_id = ? AND class_name = ? ORDER BY first_name, last_name",
            (school_id, selected_class)
        ) if selected_class else []

    if request.method == "POST":
        student_id = request.form.get("student_id")
        term_name = request.form.get("term_name")
        due_date = request.form.get("due_date")
        payment_date = request.form.get("payment_date")
        receipt_number = request.form.get("receipt_number", "").strip()

        try:
            amount = float(request.form.get("amount") or 0)
            paid_amount = float(request.form.get("paid_amount") or 0)
        except ValueError:
            flash("Amount and payment must be valid numbers.", "danger")
            return redirect(url_for("add_fee", class_name=selected_class))

        if not student_id or not term_name or amount <= 0:
            flash("Student, term, and total amount are required.", "danger")
            return redirect(url_for("add_fee", class_name=selected_class))

        student = fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        if not student:
            flash("Student not found.", "danger")
            return redirect(url_for("add_fee", class_name=selected_class))

        if role != "super_admin" and row_get(student, "school_id") != school_id:
            flash("Invalid student selected.", "danger")
            return redirect(url_for("add_fee", class_name=selected_class))

        fee_school_id = row_get(student, "school_id", school_id)

        balance = amount - paid_amount
        if balance <= 0:
            status = "Paid"
            balance = 0
        elif paid_amount > 0:
            status = "Partially Paid"
        else:
            status = "Pending"

        conn = get_db()
        cursor = conn.cursor()

        try:
            if is_postgres():
                cursor.execute(
                    convert_query("""
                        INSERT INTO fees (school_id, student_id, term_name, amount, paid_amount, balance, status, due_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        RETURNING id
                    """),
                    (fee_school_id, student_id, term_name, amount, paid_amount, balance, status, due_date),
                )
                fee_id = cursor.fetchone()["id"]
            else:
                cursor.execute(
                    convert_query("""
                        INSERT INTO fees (school_id, student_id, term_name, amount, paid_amount, balance, status, due_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """),
                    (fee_school_id, student_id, term_name, amount, paid_amount, balance, status, due_date),
                )
                fee_id = cursor.lastrowid

            if paid_amount > 0:
                cursor.execute(
                    convert_query("""
                        INSERT INTO fee_payments (school_id, fee_id, payment_date, amount_paid, receipt_number)
                        VALUES (?, ?, ?, ?, ?)
                    """),
                    (fee_school_id, fee_id, payment_date, paid_amount, receipt_number),
                )

                student_name = f"{row_get(student, 'first_name', '')} {row_get(student, 'last_name', '')}".strip() or "Student"
                cashbook_insert_income(
                    cursor,
                    fee_school_id,
                    payment_date,
                    paid_amount,
                    receipt_number,
                    student_name,
                    term_name,
                    session.get("full_name", "System")
                )

            conn.commit()
            log_audit(
    "Added fee record",
    "fees",
    fee_id,
    f"Student ID {student_id}, term {term_name}, amount {amount}, paid {paid_amount}"
)
            flash("Fee record added successfully.", "success")
            return redirect(url_for("fees"))
        except Exception as e:
            conn.rollback()
            flash(f"Error adding fee: {str(e)}", "danger")
            return redirect(url_for("add_fee", class_name=selected_class))
        finally:
            conn.close()

    return render_template(
        "add_fee.html",
        students=students,
        class_options=CLASS_OPTIONS,
        selected_class=selected_class
    )

@app.route("/update_fee/<int:fee_id>", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def update_fee(fee_id):
    school_id = session.get("school_id")
    role = session.get("role")

    base_query = """
        SELECT f.*, s.first_name, s.last_name, s.student_number, s.class_name
        FROM fees f
        JOIN students s ON f.student_id = s.id
        WHERE f.id = ?
    """
    params = [fee_id]

    if role != "super_admin":
        base_query += " AND f.school_id = ?"
        params.append(school_id)

    fee = fetch_one(base_query, tuple(params))
    if not fee:
        flash("Fee record not found or access denied.", "danger")
        return redirect(url_for("fees"))

    if request.method == "POST":
        try:
            additional_payment = float(request.form.get("additional_payment", 0) or 0)
        except ValueError:
            flash("Payment amount must be a valid number.", "danger")
            return redirect(url_for("update_fee", fee_id=fee_id))

        payment_date = request.form.get("payment_date")
        receipt_number = request.form.get("receipt_number", "").strip()

        if additional_payment <= 0:
            flash("Additional payment must be greater than zero.", "danger")
            return redirect(url_for("update_fee", fee_id=fee_id))

        new_paid_amount = float(fee["paid_amount"] or 0) + additional_payment
        total_amount = float(fee["amount"] or 0)
        new_balance = max(total_amount - new_paid_amount, 0)

        if new_balance == 0:
            status = "Paid"
        elif new_paid_amount > 0:
            status = "Partially Paid"
        else:
            status = "Pending"

        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute(
                convert_query("UPDATE fees SET paid_amount = ?, balance = ?, status = ? WHERE id = ?"),
                (new_paid_amount, new_balance, status, fee_id),
            )

            cursor.execute(
                convert_query("""
                    INSERT INTO fee_payments (school_id, fee_id, payment_date, amount_paid, receipt_number)
                    VALUES (?, ?, ?, ?, ?)
                """),
                (fee["school_id"], fee_id, payment_date, additional_payment, receipt_number),
            )

            student_name = f"{fee['first_name']} {fee['last_name']}".strip()
            cashbook_insert_income(
                cursor,
                fee["school_id"],
                payment_date,
                additional_payment,
                receipt_number,
                student_name,
                fee["term_name"],
                session.get("full_name", "System")
            )

            conn.commit()
            log_audit(
    "Recorded fee payment",
    "fees",
    fee_id,
    f"Added payment {additional_payment}, receipt {receipt_number}"
)
            flash("Fee payment updated successfully.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error updating fee payment: {str(e)}", "danger")
        finally:
            conn.close()

        return redirect(url_for("update_fee", fee_id=fee_id))

    if role == "super_admin":
        payment_history = fetch_all("SELECT * FROM fee_payments WHERE fee_id = ? ORDER BY payment_date DESC, id DESC", (fee_id,))
    else:
        payment_history = fetch_all(
            "SELECT * FROM fee_payments WHERE fee_id = ? AND school_id = ? ORDER BY payment_date DESC, id DESC",
            (fee_id, school_id),
        )

    return render_template("update_fee.html", fee=fee, payment_history=payment_history)

# =========================================================
# RESULTS
# =========================================================
@app.route("/enter_result")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def enter_result():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        students_list = fetch_all("SELECT * FROM students ORDER BY first_name, last_name")
        subjects_rows = fetch_all("SELECT * FROM subjects ORDER BY subject_name")
    else:
        students_list = fetch_all(
            "SELECT * FROM students WHERE school_id = ? ORDER BY first_name, last_name",
            (school_id,)
        )
        subjects_rows = fetch_all(
            "SELECT * FROM subjects WHERE school_id = ? ORDER BY subject_name",
            (school_id,)
        )

    subjects_list = [row["subject_name"] for row in subjects_rows]

    return render_template(
        "enter_result.html",
        class_options=CLASS_OPTIONS,
        students=students_list,
        subjects=subjects_list
    )

@app.route("/save_result", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def save_result():
    school_id = session.get("school_id")
    role = session.get("role")

    student_id = request.form.get("student_id")
    class_name = request.form.get("class_name")
    subject = request.form.get("subject")
    term = request.form.get("term")
    marks = request.form.get("marks")

    if not student_id or not class_name or not subject or not term or marks is None:
        flash("All result fields are required.", "danger")
        return redirect(url_for("enter_result"))

    if role != "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (student_id, school_id))
        if not student:
            flash("Invalid student selected.", "danger")
            return redirect(url_for("enter_result"))

    try:
        marks = float(marks)
    except ValueError:
        flash("Marks must be a valid number.", "danger")
        return redirect(url_for("enter_result"))

    if marks >= 80:
        grade = "A"
    elif marks >= 70:
        grade = "B"
    elif marks >= 60:
        grade = "C"
    elif marks >= 50:
        grade = "D"
    else:
        grade = "F"

    execute_commit(
        """
        INSERT INTO results (school_id, student_id, class_name, subject, term, marks, grade)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (school_id, student_id, class_name, subject, term, marks, grade),
    )

    flash("Result saved successfully.", "success")
    return redirect(url_for("results"))


@app.route("/results")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def results():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        result_records = fetch_all("""
            SELECT r.*, s.first_name, s.last_name, s.student_number
            FROM results r
            JOIN students s ON r.student_id = s.id
            ORDER BY s.first_name, s.last_name, r.subject
        """)
    else:
        result_records = fetch_all("""
            SELECT r.*, s.first_name, s.last_name, s.student_number
            FROM results r
            JOIN students s ON r.student_id = s.id
            WHERE r.school_id = ?
            ORDER BY s.first_name, s.last_name, r.subject
        """, (school_id,))

    return render_template("results.html", result_records=result_records)


# =========================================================
# ATTENDANCE
# =========================================================
@app.route("/attendance", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def attendance():
    school_id = session.get("school_id")
    role = session.get("role")

    selected_class = request.form.get("class_name") if request.method == "POST" else request.args.get("class_name")
    students_list = []

    if selected_class:
        if role == "super_admin":
            students_list = fetch_all("SELECT * FROM students WHERE class_name = ? ORDER BY first_name, last_name", (selected_class,))
        else:
            students_list = fetch_all(
                "SELECT * FROM students WHERE school_id = ? AND class_name = ? ORDER BY first_name, last_name",
                (school_id, selected_class),
            )

    return render_template("attendance.html", class_options=CLASS_OPTIONS, selected_class=selected_class, students=students_list)


@app.route("/save_attendance", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def save_attendance():
    school_id = session.get("school_id")
    role = session.get("role")

    class_name = request.form.get("class_name")
    date = request.form.get("date")
    student_ids = request.form.getlist("student_id")

    if not class_name or not date:
        flash("Class and date are required.", "danger")
        return redirect(url_for("attendance"))

    conn = get_db()
    cursor = conn.cursor()

    try:
        for student_id in student_ids:
            if role != "super_admin":
                student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (student_id, school_id))
                if not student:
                    continue

            status = request.form.get(f"status_{student_id}")
            cursor.execute(
                convert_query("""
                    INSERT INTO attendance (school_id, student_id, class_name, date, status)
                    VALUES (?, ?, ?, ?, ?)
                """),
                (school_id, student_id, class_name, date, status),
            )

        conn.commit()
        flash("Attendance saved successfully.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error saving attendance: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for("attendance", class_name=class_name))


@app.route("/attendance_records")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def attendance_records():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        attendance_list = fetch_all("""
            SELECT a.*, s.first_name, s.last_name, s.student_number
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            ORDER BY a.date DESC, s.first_name, s.last_name
        """)
    else:
        attendance_list = fetch_all("""
            SELECT a.*, s.first_name, s.last_name, s.student_number
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.school_id = ?
            ORDER BY a.date DESC, s.first_name, s.last_name
        """, (school_id,))

    return render_template("attendance_records.html", attendance_records=attendance_list)


# =========================================================
# ASSIGNMENTS
# =========================================================
@app.route("/assignments")
@login_required
@roles_required("school_admin", "super_admin", "teacher", "parent")
def assignments():
    school_id = session.get("school_id")
    role = session.get("role")
    user_id = session.get("user_id")

    if role == "parent":
        assignments_list = fetch_all("""
            SELECT a.*
            FROM assignments a
            JOIN students s ON a.class_name = s.class_name
            JOIN guardians g ON s.id = g.student_id
            WHERE g.parent_user_id = ? AND a.school_id = ?
            ORDER BY a.due_date ASC, a.class_name ASC, a.subject ASC
        """, (user_id, school_id))
        return render_template("parent_assignments.html", assignments=assignments_list)

    if role == "super_admin":
        assignments_list = fetch_all("SELECT * FROM assignments ORDER BY due_date ASC, class_name ASC, subject ASC")
    else:
        assignments_list = fetch_all(
            "SELECT * FROM assignments WHERE school_id = ? ORDER BY due_date ASC, class_name ASC, subject ASC",
            (school_id,),
        )

    return render_template("assignments.html", assignments=assignments_list)


@app.route("/add_assignment", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def add_assignment():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        subjects_rows = fetch_all("SELECT * FROM subjects ORDER BY subject_name")
    else:
        subjects_rows = fetch_all(
            "SELECT * FROM subjects WHERE school_id = ? ORDER BY subject_name",
            (school_id,)
        )

    subjects_list = [row["subject_name"] for row in subjects_rows]

    if request.method == "POST":
        class_name = request.form.get("class_name")
        subject = request.form.get("subject")
        title = request.form.get("title")
        description = request.form.get("description")
        due_date = request.form.get("due_date")

        if not class_name or not subject or not title or not description or not due_date:
            flash("All assignment fields are required.", "danger")
            return redirect(url_for("add_assignment"))

        execute_commit("""
            INSERT INTO assignments (school_id, class_name, subject, title, description, due_date, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (school_id, class_name, subject, title, description, due_date, session.get("full_name")))

        flash("Assignment added successfully.", "success")
        return redirect(url_for("assignments"))

    return render_template("add_assignment.html", class_options=CLASS_OPTIONS, subjects=subjects_list)


# =========================================================
# PARENT PORTAL
# =========================================================
@app.route("/parent_dashboard")
@login_required
@roles_required("parent")
def parent_dashboard():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    student = fetch_one("""
        SELECT s.*
        FROM students s
        JOIN guardians g ON s.id = g.student_id
        WHERE g.parent_user_id = ? AND s.school_id = ?
        LIMIT 1
    """, (user_id, school_id))

    fee_summary = {"total_amount": 0, "total_paid": 0, "total_balance": 0}
    if student:
        fee_summary = fetch_one("""
            SELECT
                COALESCE(SUM(amount), 0) AS total_amount,
                COALESCE(SUM(paid_amount), 0) AS total_paid,
                COALESCE(SUM(balance), 0) AS total_balance
            FROM fees
            WHERE student_id = ? AND school_id = ?
        """, (student["id"], school_id))

    return render_template("parent_dashboard.html", student=student, fee_summary=fee_summary)


@app.route("/parent_fees")
@login_required
@roles_required("parent")
def parent_fees():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    fee_records = fetch_all("""
        SELECT f.*, s.first_name, s.last_name, s.class_name
        FROM fees f
        JOIN guardians g ON f.student_id = g.student_id
        JOIN students s ON s.id = f.student_id
        WHERE g.parent_user_id = ? AND f.school_id = ?
        ORDER BY f.term_name
    """, (user_id, school_id))

    return render_template("parent_fees.html", fee_records=fee_records)


@app.route("/parent_results")
@login_required
@roles_required("parent")
def parent_results():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    student = fetch_one("""
        SELECT s.*
        FROM students s
        JOIN guardians g ON s.id = g.student_id
        WHERE g.parent_user_id = ? AND s.school_id = ?
        LIMIT 1
    """, (user_id, school_id))

    if not student:
        flash("No student linked to this parent account.", "danger")
        return redirect(url_for("parent_dashboard"))

    fee_summary = fetch_one("""
        SELECT COALESCE(SUM(balance), 0) AS total_balance
        FROM fees
        WHERE student_id = ? AND school_id = ?
    """, (student["id"], school_id))

    if fee_summary and float(fee_summary["total_balance"] or 0) > 0:
        flash("Results are not available because of outstanding fees.", "danger")
        return redirect(url_for("parent_dashboard"))

    result_records = fetch_all("""
        SELECT r.*, s.first_name, s.last_name, s.student_number
        FROM results r
        JOIN students s ON r.student_id = s.id
        WHERE r.student_id = ? AND r.school_id = ?
        ORDER BY r.term, r.subject
    """, (student["id"], school_id))

    return render_template("parent_results.html", result_records=result_records, student=student)


@app.route("/parent_attendance")
@login_required
@roles_required("parent")
def parent_attendance():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    attendance_list = fetch_all("""
        SELECT a.*, s.first_name, s.last_name, s.student_number
        FROM attendance a
        JOIN guardians g ON a.student_id = g.student_id
        JOIN students s ON s.id = a.student_id
        WHERE g.parent_user_id = ? AND a.school_id = ?
        ORDER BY a.date DESC
    """, (user_id, school_id))

    return render_template("parent_attendance.html", attendance_records=attendance_list)


@app.route("/parent_assignments")
@login_required
@roles_required("parent")
def parent_assignments():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    assignments_list = fetch_all("""
        SELECT a.*
        FROM assignments a
        JOIN students s ON a.class_name = s.class_name
        JOIN guardians g ON s.id = g.student_id
        WHERE g.parent_user_id = ? AND a.school_id = ?
        ORDER BY a.due_date ASC
    """, (user_id, school_id))

    return render_template("parent_assignments.html", assignments=assignments_list)


@app.route("/parent_setup", methods=["GET", "POST"])
def parent_setup():
    if request.method == "POST":
        student_number = request.form.get("student_number", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()

        if not student_number or not phone or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("parent_setup"))

        user = fetch_one("""
            SELECT u.id
            FROM users u
            JOIN guardians g ON u.id = g.parent_user_id
            JOIN students s ON s.id = g.student_id
            WHERE s.student_number = ? AND g.phone = ?
            LIMIT 1
        """, (student_number, phone))

        if not user:
            flash("No matching parent account was found. Check student number and phone number.", "danger")
            return redirect(url_for("parent_setup"))

        execute_commit("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(password), user["id"]))
        flash("Password set successfully. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("parent_setup.html")


# =========================================================
# TIMETABLE
# =========================================================
@app.route("/timetable")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def timetable():
    school_id = session.get("school_id")
    role = session.get("role")
    selected_class = request.args.get("class_name", "").strip()

    if role == "teacher":
        teacher = fetch_one("""
            SELECT * FROM teachers
            WHERE user_id = ? AND school_id = ?
            LIMIT 1
        """, (session["user_id"], school_id))

        timetable_rows = []
        if teacher:
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                WHERE t.school_id = ? AND t.teacher_id = ?
                ORDER BY
                    CASE t.day_of_week
                        WHEN 'Monday' THEN 1
                        WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3
                        WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5
                        WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                    END,
                    t.start_time
            """, (school_id, teacher["id"]))
        return render_template("teacher_timetable.html", timetable_rows=timetable_rows)

    if role == "super_admin":
        if selected_class:
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                WHERE t.class_name = ?
                ORDER BY
                    CASE t.day_of_week
                        WHEN 'Monday' THEN 1
                        WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3
                        WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5
                        WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                    END,
                    t.start_time
            """, (selected_class,))
        else:
            timetable_rows = []
    else:
        if selected_class:
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                WHERE t.school_id = ? AND t.class_name = ?
                ORDER BY
                    CASE t.day_of_week
                        WHEN 'Monday' THEN 1
                        WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3
                        WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5
                        WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                    END,
                    t.start_time
            """, (school_id, selected_class))
        else:
            timetable_rows = []

    return render_template(
        "timetable.html",
        class_options=CLASS_OPTIONS,
        selected_class=selected_class,
        timetable_rows=timetable_rows,
    )
@app.route("/timetable_settings", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def timetable_settings():
    school_id = session.get("school_id")
    role = session.get("role")

    schools = []
    if role == "super_admin":
        schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        start_time = request.form.get("start_time")
        period_length = request.form.get("period_length") or 35
        periods_per_day = request.form.get("periods_per_day") or 8
        break_after_period = request.form.get("break_after_period") or 3
        break_duration = request.form.get("break_duration") or 20
        lunch_after_period = request.form.get("lunch_after_period") or 5
        lunch_duration = request.form.get("lunch_duration") or 40

        existing = fetch_one(
            "SELECT * FROM timetable_settings WHERE school_id = ?",
            (school_id,)
        )

        if existing:
            execute_commit(
                """
                UPDATE timetable_settings
                SET start_time = ?, period_length = ?, periods_per_day = ?,
                    break_after_period = ?, break_duration = ?,
                    lunch_after_period = ?, lunch_duration = ?
                WHERE school_id = ?
                """,
                (
                    start_time, period_length, periods_per_day,
                    break_after_period, break_duration,
                    lunch_after_period, lunch_duration,
                    school_id
                )
            )
        else:
            execute_commit(
                """
                INSERT INTO timetable_settings (
                    school_id, start_time, period_length, periods_per_day,
                    break_after_period, break_duration,
                    lunch_after_period, lunch_duration
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    school_id, start_time, period_length, periods_per_day,
                    break_after_period, break_duration,
                    lunch_after_period, lunch_duration
                )
            )

        flash("Timetable settings saved successfully.", "success")
        return redirect(url_for("timetable_settings"))

    if role == "super_admin" and request.args.get("school_id"):
        school_id = request.args.get("school_id")

    settings = fetch_one(
        "SELECT * FROM timetable_settings WHERE school_id = ?",
        (school_id,)
    )

    return render_template(
        "timetable_settings.html",
        settings=settings,
        schools=schools
    )

@app.route("/class/<class_name>")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def class_students(class_name):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        students = fetch_all(
            "SELECT * FROM students WHERE class_name = ? ORDER BY first_name, last_name",
            (class_name,)
        )
    else:
        students = fetch_all(
            "SELECT * FROM students WHERE school_id = ? AND class_name = ? ORDER BY first_name, last_name",
            (school_id, class_name)
        )

    return render_template(
        "class_students.html",
        students=students,
        class_name=class_name
    )
@app.route("/subjects")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def subjects():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        subject_list = fetch_all("SELECT * FROM subjects ORDER BY subject_name")
    else:
        subject_list = fetch_all(
            "SELECT * FROM subjects WHERE school_id = ? ORDER BY subject_name",
            (school_id,)
        )

    return render_template("subjects.html", subjects=subject_list)

@app.route("/add_subject", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def add_subject():
    school_id = session.get("school_id")
    role = session.get("role")

    schools = fetch_all("SELECT * FROM schools ORDER BY school_name") if role == "super_admin" else []

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        subject_name = request.form.get("subject_name", "").strip()
        weekly_periods = request.form.get("weekly_periods") or 1
        preferred_session = request.form.get("preferred_session") or "any"
        is_practical = 1 if request.form.get("is_practical") == "on" else 0
        requires_double_period = 1 if request.form.get("requires_double_period") == "on" else 0
        requires_four_block = 1 if request.form.get("requires_four_block") == "on" else 0
        requires_two_block = 1 if request.form.get("requires_two_block") == "on" else 0

        if not subject_name:
            flash("Subject name is required.", "danger")
            return redirect(url_for("add_subject"))

        existing = fetch_one(
            "SELECT * FROM subjects WHERE school_id = ? AND subject_name = ?",
            (school_id, subject_name)
        )

        if existing:
            flash("Subject already exists for this school.", "danger")
            return redirect(url_for("add_subject"))

        execute_commit(
            """
            INSERT INTO subjects (
                school_id, subject_name, weekly_periods, preferred_session,
                is_practical, requires_double_period, requires_four_block, requires_two_block
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                school_id, subject_name, weekly_periods, preferred_session,
                is_practical, requires_double_period, requires_four_block, requires_two_block
            )
        )

        flash("Subject added successfully.", "success")
        return redirect(url_for("subjects"))

    return render_template("add_subject.html", schools=schools)

@app.route("/add_timetable", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def add_timetable():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        teachers_list = fetch_all("SELECT * FROM teachers ORDER BY full_name")
        subjects_rows = fetch_all("SELECT * FROM subjects ORDER BY subject_name")
    else:
        teachers_list = fetch_all("SELECT * FROM teachers WHERE school_id = ? ORDER BY full_name", (school_id,))
        subjects_rows = fetch_all(
            "SELECT * FROM subjects WHERE school_id = ? ORDER BY subject_name",
            (school_id,)
        )

    subjects = [row["subject_name"] for row in subjects_rows]


    if request.method == "POST":
        class_name = request.form.get("class_name")
        subject = request.form.get("subject")
        teacher_id = request.form.get("teacher_id")
        day_of_week = request.form.get("day_of_week")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        room = request.form.get("room", "").strip()

        if not class_name or not subject or not teacher_id or not day_of_week or not start_time or not end_time:
            flash("All timetable fields except room are required.", "danger")
            return redirect(url_for("add_timetable"))

        if end_time <= start_time:
            flash("End time must be after start time.", "danger")
            return redirect(url_for("add_timetable"))

        if role != "super_admin":
            teacher = fetch_one("SELECT * FROM teachers WHERE id = ? AND school_id = ?", (teacher_id, school_id))
            if not teacher:
                flash("Invalid teacher selected.", "danger")
                return redirect(url_for("add_timetable"))

        if role == "super_admin":
            teacher_conflict = fetch_one("""
                SELECT * FROM timetables
                WHERE teacher_id = ?
                  AND day_of_week = ?
                  AND start_time < ?
                  AND end_time > ?
            """, (teacher_id, day_of_week, end_time, start_time))
            class_conflict = fetch_one("""
                SELECT * FROM timetables
                WHERE class_name = ?
                  AND day_of_week = ?
                  AND start_time < ?
                  AND end_time > ?
            """, (class_name, day_of_week, end_time, start_time))
        else:
            teacher_conflict = fetch_one("""
                SELECT * FROM timetables
                WHERE school_id = ?
                  AND teacher_id = ?
                  AND day_of_week = ?
                  AND start_time < ?
                  AND end_time > ?
            """, (school_id, teacher_id, day_of_week, end_time, start_time))
            class_conflict = fetch_one("""
                SELECT * FROM timetables
                WHERE school_id = ?
                  AND class_name = ?
                  AND day_of_week = ?
                  AND start_time < ?
                  AND end_time > ?
            """, (school_id, class_name, day_of_week, end_time, start_time))

        if teacher_conflict:
            flash("This teacher is already assigned during that time.", "danger")
            return redirect(url_for("add_timetable"))

        if class_conflict:
            flash("This class already has a lesson during that time.", "danger")
            return redirect(url_for("add_timetable"))

        execute_commit("""
            INSERT INTO timetables (
                school_id, class_name, subject, teacher_id,
                day_of_week, start_time, end_time, room
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (school_id, class_name, subject, teacher_id, day_of_week, start_time, end_time, room))

        flash("Timetable entry added successfully.", "success")
        return redirect(url_for("timetable", class_name=class_name))

    return render_template("add_timetable.html", class_options=CLASS_OPTIONS, teachers=teachers_list, subjects=subjects)


@app.route("/print_result/<int:student_id>/<term>")
@login_required
@roles_required("school_admin", "super_admin")
def print_result(student_id, term):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        results = fetch_all("""
            SELECT * FROM results
            WHERE student_id = ? AND term = ?
            ORDER BY subject
        """, (student_id, term))
        fee_summary = fetch_one("""
            SELECT COALESCE(SUM(balance), 0) AS total_balance
            FROM fees
            WHERE student_id = ?
        """, (student_id,))
    else:
        student = fetch_one("""
            SELECT * FROM students
            WHERE id = ? AND school_id = ?
        """, (student_id, school_id))
        if not student:
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("students"))

        results = fetch_all("""
            SELECT * FROM results
            WHERE student_id = ? AND school_id = ? AND term = ?
            ORDER BY subject
        """, (student_id, school_id, term))
        fee_summary = fetch_one("""
            SELECT COALESCE(SUM(balance), 0) AS total_balance
            FROM fees
            WHERE student_id = ? AND school_id = ?
        """, (student_id, school_id))

    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("students"))

    total_marks = sum(float(r["marks"] or 0) for r in results)
    subject_count = len(results)
    average = round(total_marks / subject_count, 2) if subject_count > 0 else 0

    return render_template(
        "print_result.html",
        student=student,
        results=results,
        term=term,
        total_marks=total_marks,
        average=average,
        total_balance=float(fee_summary["total_balance"] or 0)
    )

# =========================================================
# CASHBOOK
# =========================================================

def cashbook_insert_income(cursor, school_id, payment_date, amount_paid, receipt_number, student_name, term_name, created_by):
    try:
        amount = float(amount_paid or 0)
    except Exception:
        amount = 0

    if amount <= 0:
        return

    entry_date = payment_date or datetime.now().strftime("%Y-%m-%d")

    cursor.execute(
        convert_query("""
            INSERT INTO cashbook (
                school_id, entry_date, entry_type, category, description,
                amount, payment_method, reference_number, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """),
        (
            school_id,
            entry_date,
            "income",
            "School Fees",
            f"Fee payment from {student_name} for {term_name}",
            amount,
            "School Fee Payment",
            receipt_number,
            created_by,
        )
    )


@app.route("/cashbook")
@login_required
@roles_required("school_admin", "super_admin")
def cashbook():
    school_id = session.get("school_id")
    role = session.get("role")

    entry_type = request.args.get("entry_type", "").strip()
    category = request.args.get("category", "").strip()
    source = request.args.get("source", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    query = "SELECT * FROM cashbook WHERE 1=1"
    params = []

    if role != "super_admin":
        query += " AND school_id = ?"
        params.append(school_id)

    if entry_type:
        query += " AND entry_type = ?"
        params.append(entry_type)

    if category:
        query += " AND category = ?"
        params.append(category)

    if source == "auto_fees":
        query += " AND category = ?"
        params.append("School Fees")

    elif source == "manual":
        query += " AND category != ?"
        params.append("School Fees")

    if start_date:
        query += " AND entry_date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND entry_date <= ?"
        params.append(end_date)

    query += " ORDER BY entry_date DESC, id DESC"

    entries = fetch_all(query, tuple(params))

    total_income = 0
    total_expense = 0
    running_balance = 0
    processed_entries = []

    for entry in reversed(entries):
        amount = float(entry["amount"] or 0)

        if entry["entry_type"] == "income":
            total_income += amount
            running_balance += amount
        else:
            total_expense += amount
            running_balance -= amount

        processed_entries.append({
            "id": entry["id"],
            "entry_date": entry["entry_date"],
            "entry_type": entry["entry_type"],
            "category": entry["category"],
            "description": entry["description"],
            "amount": amount,
            "payment_method": entry["payment_method"],
            "reference_number": entry["reference_number"],
            "created_by": entry["created_by"],
            "running_balance": running_balance
        })

    processed_entries.reverse()
    net_balance = total_income - total_expense

    return render_template(
        "cashbook.html",
        entries=processed_entries,
        entry_type=entry_type,
        category=category,
        source=source,
        start_date=start_date,
        end_date=end_date,
        total_income=total_income,
        total_expense=total_expense,
        net_balance=net_balance
    )


@app.route("/add_cashbook_entry", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def add_cashbook_entry():
    school_id = session.get("school_id")
    role = session.get("role")

    schools = []
    if role == "super_admin":
        schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        entry_date = request.form.get("entry_date")
        entry_type = request.form.get("entry_type")
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        amount = request.form.get("amount")
        payment_method = request.form.get("payment_method", "").strip()
        reference_number = request.form.get("reference_number", "").strip()
        created_by = session.get("full_name", "System")

        if not school_id or not entry_date or not entry_type or not category or not amount:
            flash("School, date, type, category, and amount are required.", "danger")
            return redirect(url_for("add_cashbook_entry"))

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except Exception:
            flash("Amount must be greater than zero.", "danger")
            return redirect(url_for("add_cashbook_entry"))

        execute_commit("""
            INSERT INTO cashbook (
                school_id, entry_date, entry_type, category, description,
                amount, payment_method, reference_number, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            school_id,
            entry_date,
            entry_type,
            category,
            description,
            amount,
            payment_method,
            reference_number,
            created_by
        ))

        log_audit(
            "Added cashbook entry",
            "cashbook",
            None,
            f"{entry_type} - {category} - Amount {amount}"
        )

        flash("Cashbook entry added successfully.", "success")
        return redirect(url_for("cashbook"))

    return render_template("add_cashbook_entry.html", schools=schools)


@app.route("/cashbook_reports")
@login_required
@roles_required("school_admin", "super_admin")
def cashbook_reports():
    school_id = session.get("school_id")
    role = session.get("role")

    report_type = request.args.get("report_type", "daily").strip()
    selected_date = request.args.get("date", datetime.now().strftime("%Y-%m-%d")).strip()
    selected_month = request.args.get("month", datetime.now().strftime("%Y-%m")).strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    entry_type = request.args.get("entry_type", "").strip()
    category = request.args.get("category", "").strip()
    source = request.args.get("source", "").strip()

    query = "SELECT * FROM cashbook WHERE 1=1"
    params = []

    if role != "super_admin":
        query += " AND school_id = ?"
        params.append(school_id)

    if report_type == "daily":
        query += " AND entry_date = ?"
        params.append(selected_date)

    elif report_type == "monthly":
        query += " AND entry_date LIKE ?"
        params.append(f"{selected_month}%")

    elif report_type == "custom":
        if start_date:
            query += " AND entry_date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND entry_date <= ?"
            params.append(end_date)

    if entry_type:
        query += " AND entry_type = ?"
        params.append(entry_type)

    if category:
        query += " AND category = ?"
        params.append(category)

    if source == "auto_fees":
        query += " AND category = ?"
        params.append("School Fees")

    elif source == "manual":
        query += " AND category != ?"
        params.append("School Fees")

    query += " ORDER BY entry_date ASC, id ASC"

    entries = fetch_all(query, tuple(params))

    total_income = 0
    total_expense = 0
    running_balance = 0
    processed_entries = []

    for entry in entries:
        amount = float(entry["amount"] or 0)

        if entry["entry_type"] == "income":
            total_income += amount
            running_balance += amount
        else:
            total_expense += amount
            running_balance -= amount

        processed_entries.append({
            "id": entry["id"],
            "entry_date": entry["entry_date"],
            "entry_type": entry["entry_type"],
            "category": entry["category"],
            "description": entry["description"],
            "amount": amount,
            "payment_method": entry["payment_method"],
            "reference_number": entry["reference_number"],
            "created_by": entry["created_by"],
            "running_balance": running_balance
        })

    net_balance = total_income - total_expense

    return render_template(
        "cashbook_reports.html",
        entries=processed_entries,
        report_type=report_type,
        selected_date=selected_date,
        selected_month=selected_month,
        start_date=start_date,
        end_date=end_date,
        entry_type=entry_type,
        category=category,
        source=source,
        total_income=total_income,
        total_expense=total_expense,
        net_balance=net_balance
    )
@app.route("/classes")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def classes():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        class_rows = fetch_all("""
            SELECT 
                sc.id,
                sc.school_id,
                sc.class_name,
                s.school_name,
                COUNT(st.id) AS total_students
            FROM school_classes sc
            LEFT JOIN schools s ON sc.school_id = s.id
            LEFT JOIN students st 
                ON st.school_id = sc.school_id 
                AND st.class_name = sc.class_name
            GROUP BY sc.id, sc.school_id, sc.class_name, s.school_name
            ORDER BY s.school_name, sc.class_name
        """)
    else:
        class_rows = fetch_all("""
            SELECT 
                sc.id,
                sc.school_id,
                sc.class_name,
                COUNT(st.id) AS total_students
            FROM school_classes sc
            LEFT JOIN students st 
                ON st.school_id = sc.school_id 
                AND st.class_name = sc.class_name
            WHERE sc.school_id = ?
            GROUP BY sc.id, sc.school_id, sc.class_name
            ORDER BY sc.class_name
        """, (school_id,))

    return render_template("classes.html", classes=class_rows)

@app.route("/add_class", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def add_class():
    role = session.get("role")
    school_id = session.get("school_id")

    schools = fetch_all("SELECT * FROM schools ORDER BY school_name") if role == "super_admin" else []

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        class_name = request.form.get("class_name", "").strip()

        if not school_id or not class_name:
            flash("School and class name are required.", "danger")
            return redirect(url_for("add_class"))

        try:
            execute_commit(
                "INSERT INTO school_classes (school_id, class_name) VALUES (?, ?)",
                (school_id, class_name)
            )
            flash("Class added successfully.", "success")
        except Exception:
            flash("That class already exists for this school.", "warning")

        return redirect(url_for("classes"))

    return render_template("add_class.html", schools=schools)

@app.route("/print_class_list/<class_name>")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def print_class_list(class_name):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        students = fetch_all("""
            SELECT * FROM students
            WHERE class_name = ?
            ORDER BY first_name, last_name
        """, (class_name,))
    else:
        students = fetch_all("""
            SELECT * FROM students
            WHERE school_id = ? AND class_name = ?
            ORDER BY first_name, last_name
        """, (school_id, class_name))

    return render_template(
        "print_class_list.html",
        students=students,
        class_name=class_name
    )

@app.route("/school_settings", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def school_settings():
    role = session.get("role")
    school_id = session.get("school_id")

    schools = fetch_all("SELECT * FROM schools ORDER BY school_name") if role == "super_admin" else []

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        display_name = request.form.get("display_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        report_header = request.form.get("report_header", "").strip()
        logo_url = request.form.get("logo_url", "").strip()

        if not school_id:
            flash("School is required.", "danger")
            return redirect(url_for("school_settings"))

        existing = fetch_one("SELECT * FROM school_settings WHERE school_id = ?", (school_id,))

        if existing:
            execute_commit("""
                UPDATE school_settings
                SET display_name = ?, phone = ?, email = ?, address = ?, report_header = ?, logo_url = ?
                WHERE school_id = ?
            """, (display_name, phone, email, address, report_header, logo_url, school_id))
        else:
            execute_commit("""
                INSERT INTO school_settings (
                    school_id, display_name, phone, email, address, report_header, logo_url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (school_id, display_name, phone, email, address, report_header, logo_url))

        flash("School settings saved successfully.", "success")
        return redirect(url_for("school_settings"))

    selected_school_id = request.args.get("school_id") if role == "super_admin" else school_id
    settings = get_school_settings(selected_school_id) if selected_school_id else None

    return render_template(
        "school_settings.html",
        settings=settings,
        schools=schools,
        selected_school_id=selected_school_id
    )
@app.route("/billing_dashboard")
@login_required
@roles_required("super_admin")
def billing_dashboard():
    schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    summary = {
        "total_schools": len(schools),
        "active_schools": 0,
        "suspended_schools": 0,
        "overdue_schools": 0,
        "trial_schools": 0
    }

    processed = []
    today = datetime.now().date()

    for school in schools:
        end_date = parse_date_safe(row_get(school, "subscription_end_date"))
        overdue = bool(end_date and end_date < today)

        status = row_get(school, "subscription_status", "active") or "active"
        if overdue:
            status = "overdue"

        if status == "active":
            summary["active_schools"] += 1
        elif status == "suspended":
            summary["suspended_schools"] += 1
        elif status == "overdue":
            summary["overdue_schools"] += 1
        elif status == "trial":
            summary["trial_schools"] += 1

        processed.append({
            "id": school["id"],
            "school_name": school["school_name"],
            "school_code": school["school_code"],
            "subscription_status": status,
            "subscription_end_date": row_get(school, "subscription_end_date"),
            "is_active": row_get(school, "is_active", 1),
        })

    return render_template(
        "billing_dashboard.html",
        schools=processed,
        summary=summary
    )
@app.route("/school/<int:school_id>")
@login_required
@roles_required("super_admin")
def school_profile(school_id):
    school = fetch_one("SELECT * FROM schools WHERE id = ?", (school_id,))

    if not school:
        flash("School not found.", "danger")
        return redirect(url_for("schools"))

    total_students = fetch_one(
        "SELECT COUNT(*) AS total FROM students WHERE school_id = ?",
        (school_id,)
    )["total"]

    total_teachers = fetch_one(
        "SELECT COUNT(*) AS total FROM teachers WHERE school_id = ?",
        (school_id,)
    )["total"]

    total_users = fetch_one(
        "SELECT COUNT(*) AS total FROM users WHERE school_id = ?",
        (school_id,)
    )["total"]

    total_fee_records = fetch_one(
        "SELECT COUNT(*) AS total FROM fees WHERE school_id = ?",
        (school_id,)
    )["total"]

    fee_totals = fetch_one("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_billed,
            COALESCE(SUM(paid_amount), 0) AS total_paid,
            COALESCE(SUM(balance), 0) AS total_balance
        FROM fees
        WHERE school_id = ?
    """, (school_id,))

    return render_template(
        "school_profile.html",
        school=school,
        total_students=total_students,
        total_teachers=total_teachers,
        total_users=total_users,
        total_fee_records=total_fee_records,
        total_billed=fee_totals["total_billed"] or 0,
        total_paid=fee_totals["total_paid"] or 0,
        total_balance=fee_totals["total_balance"] or 0
    )
@app.route("/users")
@login_required
@roles_required("school_admin", "super_admin")
def users():
    school_id = session.get("school_id")
    role = session.get("role")
    search = request.args.get("search", "").strip()
    class_filter = request.args.get("class_name", "").strip()
    role_filter = request.args.get("role", "").strip()

    query = """
        SELECT 
            u.*,
            s.school_name,
            st.first_name AS student_first_name,
            st.last_name AS student_last_name,
            st.class_name AS student_class
        FROM users u
        LEFT JOIN schools s ON u.school_id = s.id
        LEFT JOIN guardians g ON u.id = g.parent_user_id
        LEFT JOIN students st ON g.student_id = st.id
        WHERE 1=1
    """
    params = []

    if role != "super_admin":
        query += " AND u.school_id = ? AND u.role IN ('teacher', 'parent')"
        params.append(school_id)

    if search:
        query += """
            AND (
                u.full_name LIKE ? OR 
                u.username LIKE ? OR 
                st.first_name LIKE ? OR 
                st.last_name LIKE ? OR
                st.student_number LIKE ?
            )
        """
        like = f"%{search}%"
        params.extend([like, like, like, like, like])

    if class_filter:
        query += " AND st.class_name = ?"
        params.append(class_filter)

    if role_filter:
        query += " AND u.role = ?"
        params.append(role_filter)

    query += " ORDER BY u.role, st.class_name, u.full_name"

    user_list = fetch_all(query, tuple(params))

    teacher_users = []
    parent_users = []
    admin_users = []
    other_users = []

    for user in user_list:
        if user["role"] == "teacher":
            teacher_users.append(user)
        elif user["role"] == "parent":
            parent_users.append(user)
        elif user["role"] in ["school_admin", "super_admin"]:
            admin_users.append(user)
        else:
            other_users.append(user)

    return render_template(
        "users.html",
        users=user_list,
        teacher_users=teacher_users,
        parent_users=parent_users,
        admin_users=admin_users,
        other_users=other_users,
        search=search,
        class_filter=class_filter,
        role_filter=role_filter,
        class_options=CLASS_OPTIONS
    )
@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def edit_user(user_id):
    school_id = session.get("school_id")
    current_role = session.get("role")

    # Fetch user safely
    if current_role == "super_admin":
        user = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    else:
        user = fetch_one(
            "SELECT * FROM users WHERE id = ? AND school_id = ?",
            (user_id, school_id)
        )

    if not user:
        flash("User not found or access denied.", "danger")
        return redirect(url_for("users"))

    # 🔐 Protect super admin
    if user["role"] == "super_admin" and current_role != "super_admin":
        flash("Only super admin can edit a super admin account.", "danger")
        return redirect(url_for("users"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        new_role = request.form.get("role", "").strip()
        password = request.form.get("password", "").strip()

        # 🚫 Prevent changing super admin role
        if user["role"] == "super_admin" and new_role != "super_admin":
            flash("You cannot change a super admin's role.", "danger")
            return redirect(url_for("users"))

        # 🚫 Prevent normal admins assigning high roles
        if current_role != "super_admin" and new_role in ["super_admin", "school_admin"]:
            flash("You are not allowed to assign admin roles.", "danger")
            return redirect(url_for("users"))

        # Update user
        if password:
            execute_commit("""
                UPDATE users
                SET full_name = ?, username = ?, role = ?, password = ?
                WHERE id = ?
            """, (
                full_name,
                username,
                new_role,
                generate_password_hash(password),
                user_id
            ))
        else:
            execute_commit("""
                UPDATE users
                SET full_name = ?, username = ?, role = ?
                WHERE id = ?
            """, (
                full_name,
                username,
                new_role,
                user_id
            ))

        # 📜 Audit log (if you added audit system)
        try:
            log_audit(
                action="Edited user",
                table_name="users",
                record_id=user_id,
                details=f"Updated {username} role to {new_role}"
            )
        except:
            pass

        flash("User updated successfully.", "success")
        return redirect(url_for("users"))

    return render_template("edit_user.html", user=user)

@app.route("/reset_user_password/<int:user_id>", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def reset_user_password(user_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        user = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        
        if user["role"] == "super_admin" and session.get("role") != "super_admin":
            flash("Only super admin can reset a super admin password.", "danger")
            return redirect(url_for("users"))
    else:
        user = fetch_one(
            "SELECT * FROM users WHERE id = ? AND school_id = ?",
            (user_id, school_id)
        )

    if not user:
        flash("User not found or access denied.", "danger")
        return redirect(url_for("users"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not new_password or new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("reset_user_password", user_id=user_id))
        

        execute_commit(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id)
        )

        flash("Password reset successfully.", "success")
        return redirect(url_for("users"))

    return render_template("reset_user_password.html", user=user)

@app.route("/update_school_subscription/<int:school_id>", methods=["GET", "POST"])
@login_required
@roles_required("super_admin")
def update_school_subscription(school_id):
    school = fetch_one("SELECT * FROM schools WHERE id = ?", (school_id,))

    if not school:
        flash("School not found.", "danger")
        return redirect(url_for("schools"))

    if request.method == "POST":
        subscription_end_date = request.form.get("subscription_end_date")
        subscription_status = request.form.get("subscription_status", "active").strip()

        is_active = 1 if subscription_status in ["active", "trial"] else 0

        execute_commit(
            """
            UPDATE schools
            SET subscription_end_date = ?, subscription_status = ?, is_active = ?
            WHERE id = ?
            """,
            (subscription_end_date, subscription_status, is_active, school_id)
        )

        flash("School subscription updated successfully.", "success")
        return redirect(url_for("school_profile", school_id=school_id))

    return render_template("update_school_subscription.html", school=school)

@app.route("/deactivate_user/<int:user_id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def deactivate_user(user_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "school_admin":
        user = fetch_one(
            "SELECT * FROM users WHERE id = ? AND school_id = ? AND role IN ('teacher', 'parent')",
            (user_id, school_id)
        )
    else:
        user = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    if not user:
        flash("User not found or access denied.", "danger")
        return redirect(url_for("users"))

    if user["role"] == "super_admin":
        flash("You cannot deactivate a super admin account.", "danger")
        return redirect(url_for("users"))

    execute_commit("UPDATE users SET is_active = ? WHERE id = ?", (0, user_id))
    flash("User deactivated successfully.", "success")
    return redirect(url_for("users"))


@app.route("/activate_user/<int:user_id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def activate_user(user_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "school_admin":
        user = fetch_one(
            "SELECT * FROM users WHERE id = ? AND school_id = ? AND role IN ('teacher', 'parent')",
            (user_id, school_id)
        )
    else:
        user = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    if not user:
        flash("User not found or access denied.", "danger")
        return redirect(url_for("users"))

    execute_commit("UPDATE users SET is_active = ? WHERE id = ?", (1, user_id))
    flash("User activated successfully.", "success")
    return redirect(url_for("users"))


@app.route("/deactivate_student/<int:student_id>", methods=["POST"])
@login_required
@roles_required("super_admin", "school_admin")
def deactivate_student(student_id):
    execute_commit(
        "UPDATE students SET current_status = ? WHERE id = ?",
        ("Inactive", student_id)
    )

    log_audit(
        action="Deactivated student",
        table_name="students",
        record_id=student_id,
        details="Student status changed to Inactive"
    )

    flash("Student deactivated successfully.", "success")
    return redirect(url_for("students"))


@app.route("/reactivate_student/<int:student_id>", methods=["POST"])
@login_required
@roles_required("super_admin", "school_admin")
def reactivate_student(student_id):
    execute_commit(
        "UPDATE students SET current_status = ? WHERE id = ?",
        ("Active", student_id)
    )

    log_audit(
        action="Reactivated student",
        table_name="students",
        record_id=student_id,
        details="Student status changed to Active"
    )

    flash("Student reactivated successfully.", "success")
    return redirect(url_for("students"))


@app.route("/print_all_students")
@login_required
@roles_required("school_admin", "super_admin")
def print_all_students():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        students = fetch_all("""
            SELECT * FROM students
            ORDER BY class_name, first_name, last_name
        """)
    else:
        students = fetch_all("""
            SELECT * FROM students
            WHERE school_id = ?
            ORDER BY class_name, first_name, last_name
        """, (school_id,))

    return render_template("print_all_students.html", students=students)
def run_users_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1")
        else:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
            except Exception:
                pass

        conn.commit()
    finally:
        conn.close()


@app.route("/send_fee_reminder/<int:student_id>")
@login_required
@roles_required("school_admin", "super_admin")
def send_fee_reminder(student_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    else:
        student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (student_id, school_id))

    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("students"))

    if role == "super_admin":
        fee = fetch_one("""
            SELECT COALESCE(SUM(balance), 0) AS total_balance
            FROM fees WHERE student_id = ?
        """, (student_id,))
    else:
        fee = fetch_one("""
            SELECT COALESCE(SUM(balance), 0) AS total_balance
            FROM fees WHERE student_id = ? AND school_id = ?
        """, (student_id, school_id))

    balance = float(fee["total_balance"] or 0)
    if balance <= 0:
        flash("This student has no outstanding balance.", "success")
        return redirect(url_for("student_profile", id=student_id))

    phone = student["guardian1_phone"]
    if not phone:
        flash("No guardian phone number found.", "danger")
        return redirect(url_for("student_profile", id=student_id))

    phone = phone.replace(" ", "")
    message = f"""
Dear Parent,

This is a reminder that {student['first_name']} {student['last_name']} has an outstanding school fee balance of ${balance}.

Please make payment as soon as possible.

Thank you.
""".strip()

    encoded_message = urllib.parse.quote(message)
    whatsapp_link = f"https://wa.me/{phone}?text={encoded_message}"
    return redirect(whatsapp_link)

def run_subjects_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subjects (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER,
                    subject_name VARCHAR(100) NOT NULL
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subjects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER,
                    subject_name TEXT NOT NULL
                )
            """)

        conn.commit()
    finally:
        conn.close()

def log_audit(action, table_name=None, record_id=None, details=None):
    try:
        execute_commit("""
            INSERT INTO audit_logs (
                user_id, username, role, action, table_name, record_id, details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get("user_id"),
            session.get("username") or session.get("full_name"),
            session.get("role"),
            action,
            table_name,
            record_id,
            details
        ))
    except Exception as e:
        print("Audit log error:", e)


def run_timetable_foundation_migrations():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS timetable_settings (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER UNIQUE,
                    start_time VARCHAR(20),
                    period_length INTEGER DEFAULT 35,
                    periods_per_day INTEGER DEFAULT 8,
                    break_after_period INTEGER DEFAULT 3,
                    break_duration INTEGER DEFAULT 20,
                    lunch_after_period INTEGER DEFAULT 5,
                    lunch_duration INTEGER DEFAULT 40
                )
            """)

            statements = [
                "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS weekly_periods INTEGER DEFAULT 1",
                "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS preferred_session VARCHAR(20) DEFAULT 'any'",
                "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS is_practical INTEGER DEFAULT 0",
                "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS requires_double_period INTEGER DEFAULT 0",
                "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS requires_four_block INTEGER DEFAULT 0",
                "ALTER TABLE subjects ADD COLUMN IF NOT EXISTS requires_two_block INTEGER DEFAULT 0"
            ]

            for stmt in statements:
                cursor.execute(stmt)

        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS timetable_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER UNIQUE,
                    start_time TEXT,
                    period_length INTEGER DEFAULT 35,
                    periods_per_day INTEGER DEFAULT 8,
                    break_after_period INTEGER DEFAULT 3,
                    break_duration INTEGER DEFAULT 20,
                    lunch_after_period INTEGER DEFAULT 5,
                    lunch_duration INTEGER DEFAULT 40
                )
            """)

            sqlite_statements = [
                "ALTER TABLE subjects ADD COLUMN weekly_periods INTEGER DEFAULT 1",
                "ALTER TABLE subjects ADD COLUMN preferred_session TEXT DEFAULT 'any'",
                "ALTER TABLE subjects ADD COLUMN is_practical INTEGER DEFAULT 0",
                "ALTER TABLE subjects ADD COLUMN requires_double_period INTEGER DEFAULT 0",
                "ALTER TABLE subjects ADD COLUMN requires_four_block INTEGER DEFAULT 0",
                "ALTER TABLE subjects ADD COLUMN requires_two_block INTEGER DEFAULT 0"
            ]

            for stmt in sqlite_statements:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass

        conn.commit()
    finally:
        conn.close()

        
def run_school_settings_migration():
    conn = get_db()
    cursor = conn.cursor()
    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS school_settings (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER UNIQUE,
                    display_name VARCHAR(255),
                    phone VARCHAR(100),
                    email VARCHAR(255),
                    address TEXT,
                    report_header TEXT,
                    logo_url TEXT
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS school_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER UNIQUE,
                    display_name TEXT,
                    phone TEXT,
                    email TEXT,
                    address TEXT,
                    report_header TEXT,
                    logo_url TEXT
                )
            """)
        conn.commit()
    finally:
        conn.close()


def run_school_control_migration():
    conn = get_db()
    cursor = conn.cursor()
    try:
        if is_postgres():
            statements = [
                "ALTER TABLE schools ADD COLUMN IF NOT EXISTS is_active INTEGER DEFAULT 1",
                "ALTER TABLE schools ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT 'active'",
                "ALTER TABLE schools ADD COLUMN IF NOT EXISTS subscription_end_date VARCHAR(50)"
            ]
            for stmt in statements:
                cursor.execute(stmt)
        else:
            statements = [
                "ALTER TABLE schools ADD COLUMN is_active INTEGER DEFAULT 1",
                "ALTER TABLE schools ADD COLUMN subscription_status TEXT DEFAULT 'active'",
                "ALTER TABLE schools ADD COLUMN subscription_end_date TEXT"
            ]
            for stmt in statements:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass
        conn.commit()
    finally:
        conn.close()


def run_cashbook_migration():
    """Create/repair the cashbook table.

    This supports the current cashbook design used by:
    - /cashbook
    - /add_cashbook_entry
    - /cashbook_reports
    - automatic fee payment income entries
    """
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cashbook (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER,
                    entry_date VARCHAR(50),
                    entry_type VARCHAR(20),
                    category VARCHAR(100),
                    description TEXT,
                    amount NUMERIC(12,2),
                    payment_method VARCHAR(50),
                    reference_number VARCHAR(100),
                    created_by VARCHAR(255)
                )
            """)

            statements = [
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS school_id INTEGER",
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS entry_date VARCHAR(50)",
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS entry_type VARCHAR(20)",
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS category VARCHAR(100)",
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS description TEXT",
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS amount NUMERIC(12,2)",
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50)",
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS reference_number VARCHAR(100)",
                "ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS created_by VARCHAR(255)",
            ]
            for stmt in statements:
                cursor.execute(stmt)

            # If an older table used date/type/recorded_by, copy those values into the new columns when possible.
            cursor.execute("UPDATE cashbook SET entry_date = date WHERE entry_date IS NULL AND date IS NOT NULL")
            cursor.execute("UPDATE cashbook SET entry_type = type WHERE entry_type IS NULL AND type IS NOT NULL")
            cursor.execute("UPDATE cashbook SET created_by = recorded_by WHERE created_by IS NULL AND recorded_by IS NOT NULL")
            cursor.execute("UPDATE cashbook SET category = 'General' WHERE category IS NULL OR category = ''")
            cursor.execute("UPDATE cashbook SET payment_method = '' WHERE payment_method IS NULL")
            cursor.execute("UPDATE cashbook SET reference_number = '' WHERE reference_number IS NULL")

        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cashbook (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER,
                    entry_date TEXT,
                    entry_type TEXT,
                    category TEXT,
                    description TEXT,
                    amount REAL,
                    payment_method TEXT,
                    reference_number TEXT,
                    created_by TEXT
                )
            """)

            sqlite_statements = [
                "ALTER TABLE cashbook ADD COLUMN school_id INTEGER",
                "ALTER TABLE cashbook ADD COLUMN entry_date TEXT",
                "ALTER TABLE cashbook ADD COLUMN entry_type TEXT",
                "ALTER TABLE cashbook ADD COLUMN category TEXT",
                "ALTER TABLE cashbook ADD COLUMN payment_method TEXT",
                "ALTER TABLE cashbook ADD COLUMN reference_number TEXT",
                "ALTER TABLE cashbook ADD COLUMN created_by TEXT",
            ]
            for stmt in sqlite_statements:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass

            # If an older table used date/type/recorded_by, copy those values into the new columns when possible.
            try:
                cursor.execute("UPDATE cashbook SET entry_date = date WHERE entry_date IS NULL AND date IS NOT NULL")
            except Exception:
                pass
            try:
                cursor.execute("UPDATE cashbook SET entry_type = type WHERE entry_type IS NULL AND type IS NOT NULL")
            except Exception:
                pass
            try:
                cursor.execute("UPDATE cashbook SET created_by = recorded_by WHERE created_by IS NULL AND recorded_by IS NOT NULL")
            except Exception:
                pass
            cursor.execute("UPDATE cashbook SET category = 'General' WHERE category IS NULL OR category = ''")
            cursor.execute("UPDATE cashbook SET payment_method = '' WHERE payment_method IS NULL")
            cursor.execute("UPDATE cashbook SET reference_number = '' WHERE reference_number IS NULL")

        conn.commit()
    finally:
        conn.close()

def update_school_subscription_states():
    try:
        school_list = fetch_all("SELECT * FROM schools")
    except Exception:
        return

    today = datetime.now().date()
    for school in school_list:
        end_date = parse_date_safe(row_get(school, "subscription_end_date"))
        if not end_date:
            continue

        if end_date < today:
            execute_commit(
                "UPDATE schools SET is_active = ?, subscription_status = ? WHERE id = ?",
                (0, "overdue", school["id"])
            )
        elif row_get(school, "subscription_status") == "overdue":
            execute_commit(
                "UPDATE schools SET is_active = ?, subscription_status = ? WHERE id = ?",
                (1, "active", school["id"])
            )

def run_audit_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    username VARCHAR(255),
                    role VARCHAR(50),
                    action VARCHAR(255) NOT NULL,
                    table_name VARCHAR(100),
                    record_id INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    role TEXT,
                    action TEXT NOT NULL,
                    table_name TEXT,
                    record_id INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()
    finally:
        conn.close()           

def setup_app():
    try:
        print("Starting setup...")
        with app.app_context():
            init_db()
            print("DB initialized")

            run_migrations()
            print("Migrations completed")

            run_subjects_migration()
            print("Subjects migration completed")

            run_timetable_foundation_migrations()
            print("Timetable foundation migrations completed")

            run_school_settings_migration()
            print("School settings migration completed")

            run_school_control_migration()
            print("School control migration completed")

            run_cashbook_migration()
            print("Cashbook migration completed")
            
            run_classes_migration()
            print("Classes migration completed")

            run_users_migration()
            print("Users migration completed")

            run_audit_migration()
            print("Audit migration completed")
            
            create_default_school()
            print("Default school ready")

            assign_existing_data_to_default_school()
            print("Old data linked to default school")

            migrate_roles()
            print("Roles migrated")

            create_super_admin()
            print("Super admin ready")

            update_school_subscription_states()
            print("School subscription states updated")

        print("Setup complete")
    except Exception as e:
        print("SETUP ERROR:", e)


def run_audit_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    username VARCHAR(255),
                    role VARCHAR(50),
                    action VARCHAR(255) NOT NULL,
                    table_name VARCHAR(100),
                    record_id INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    role TEXT,
                    action TEXT NOT NULL,
                    table_name TEXT,
                    record_id INTEGER,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()
    finally:
        conn.close()

def run_classes_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS school_classes (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER,
                    class_name VARCHAR(100),
                    UNIQUE(school_id, class_name)
                )
            """)

            cursor.execute("""
                INSERT INTO school_classes (school_id, class_name)
                SELECT DISTINCT school_id, class_name
                FROM students
                WHERE school_id IS NOT NULL
                  AND class_name IS NOT NULL
                  AND class_name != ''
                ON CONFLICT (school_id, class_name) DO NOTHING
            """)

        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS school_classes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER,
                    class_name TEXT,
                    UNIQUE(school_id, class_name)
                )
            """)

            cursor.execute("""
                INSERT OR IGNORE INTO school_classes (school_id, class_name)
                SELECT DISTINCT school_id, class_name
                FROM students
                WHERE school_id IS NOT NULL
                  AND class_name IS NOT NULL
                  AND class_name != ''
            """)

        conn.commit()

    finally:
        conn.close()

@app.route("/subscription_expired")
def subscription_expired():
    school = None
    school_id = session.get("school_id")
    if school_id:
        school = fetch_one("SELECT * FROM schools WHERE id = ?", (school_id,))
    return render_template("subscription_expired.html", school=school)

@app.route("/fix_old_data_school")
@login_required
@roles_required("super_admin")
def fix_old_data_school():
    school = fetch_one("SELECT * FROM schools WHERE school_code = ?", ("SCH001",))

    if not school:
        flash("Default school not found.", "danger")
        return redirect(url_for("dashboard"))

    school_id = school["id"]

    execute_commit("UPDATE users SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE students SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE teachers SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE guardians SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE fees SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE results SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE attendance SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE teacher_assignments SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE assignments SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE fee_payments SET school_id = ? WHERE school_id IS NULL", (school_id,))
    execute_commit("UPDATE timetables SET school_id = ? WHERE school_id IS NULL", (school_id,))

    flash("Old data has been assigned to the default school.", "success")
    return redirect(url_for("dashboard"))

@app.route("/suspend_school/<int:school_id>", methods=["POST"])
@login_required
@roles_required("super_admin")
def suspend_school(school_id):
    execute_commit(
        "UPDATE schools SET is_active = ?, subscription_status = ? WHERE id = ?",
        (0, "suspended", school_id)
    )
    flash("School suspended successfully.", "success")
    return redirect(url_for("schools"))


@app.route("/activate_school/<int:school_id>", methods=["POST"])
@login_required
@roles_required("super_admin")
def activate_school(school_id):
    execute_commit(
        "UPDATE schools SET is_active = ?, subscription_status = ? WHERE id = ?",
        (1, "active", school_id)
    )
    flash("School activated successfully.", "success")
    return redirect(url_for("schools"))

setup_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=not is_postgres())