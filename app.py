from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import sqlite3
import random
import string
import urllib.parse
from functools import wraps
from datetime import datetime, date
import csv
from io import StringIO
from flask import Response
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
from utils.db import (
    DB_PATH,
    is_postgres,
    get_db,
    convert_query,
    fetch_one,
    fetch_all,
    execute_commit,
    insert_and_get_id
)
from utils.auth import login_required, roles_required
from utils.audit import log_audit, run_audit_migration
from utils.helpers import (
    CLASS_OPTIONS,
    generate_student_number,
    generate_teacher_id,
    row_get,
    parse_date_safe,
    get_next_class
)
from routes.students import register_student_routes
from routes.applications import (
    register_application_routes,
    run_waiting_list_migration
)
from routes.fees import register_fee_routes
UPLOAD_FOLDER = os.path.join("static", "uploads", "resources")
ALLOWED_RESOURCE_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "png", "jpg", "jpeg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

LOGO_UPLOAD_FOLDER = os.path.join("static", "uploads", "logos")
ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

os.makedirs(LOGO_UPLOAD_FOLDER, exist_ok=True)


def allowed_logo_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS

app = Flask(__name__)

@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.secret_key = os.environ.get("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("SECRET_KEY is not set")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true"
)
register_student_routes(app)
register_application_routes(app)
register_fee_routes(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "school_v2.db")





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
        receipt_number VARCHAR(100),
        details TEXT
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
        cursor.execute("""
    CREATE TABLE IF NOT EXISTS notices (
        id SERIAL PRIMARY KEY,
        school_id INTEGER,
        class_name VARCHAR(100),
        title TEXT,
        message TEXT,
        date DATE,
        created_by TEXT
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
def create_notices_table():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notices (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER,
                    class_name VARCHAR(100),
                    title TEXT,
                    message TEXT,
                    date DATE,
                    created_by TEXT
                )
            """)
            cursor.execute("ALTER TABLE notices ADD COLUMN IF NOT EXISTS class_name VARCHAR(100)")
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER,
                    class_name TEXT,
                    title TEXT,
                    message TEXT,
                    date TEXT,
                    created_by TEXT
                )
            """)
            try:
                cursor.execute("ALTER TABLE notices ADD COLUMN class_name TEXT")
            except Exception:
                pass

        conn.commit()
    finally:
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

def add_class_teacher_column():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                ALTER TABLE school_classes
                ADD COLUMN IF NOT EXISTS class_teacher_id INTEGER
            """)
        else:
            try:
                cursor.execute("""
                    ALTER TABLE school_classes
                    ADD COLUMN class_teacher_id INTEGER
                """)
            except Exception:
                pass

        conn.commit()
    finally:
        conn.close()

def create_assessments_table():
    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assessments (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                school_id INTEGER,
                class_name VARCHAR(50),
                subject VARCHAR(100),
                term VARCHAR(20),
                assessment_type VARCHAR(50),
                marks FLOAT,
                total_marks FLOAT,
                percentage FLOAT,
                comment TEXT,
                date DATE
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                school_id INTEGER,
                class_name TEXT,
                subject TEXT,
                term TEXT,
                assessment_type TEXT,
                marks REAL,
                total_marks REAL,
                percentage REAL,
                comment TEXT,
                date TEXT
            )
        """)

    conn.commit()
    conn.close()

# =========================================================
# HELPERS
# =========================================================

def delete_by_scope(cursor, query, params):
    cursor.execute(convert_query(query), params)


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


def get_school_classes(school_id):
    rows = fetch_all(
        "SELECT * FROM school_classes WHERE school_id = ? ORDER BY class_name",
        (school_id,)
    )

    if rows:
        return [row["class_name"] for row in rows]

    return CLASS_OPTIONS

def add_school_id_to_audit_logs():
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            ALTER TABLE audit_logs
            ADD COLUMN IF NOT EXISTS school_id INTEGER
        """)

        conn.commit()
        print("audit_logs.school_id added successfully")

    except Exception as e:
        conn.rollback()
        print("Audit migration error:", e)

    finally:
        conn.close()
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

        if not user:
            flash("Invalid login details.", "danger")
            return redirect(url_for("login"))

        if int(row_get(user, "is_active", 1) or 1) != 1:
            flash("This account has been deactivated. Please contact the school administrator.", "danger")
            return redirect(url_for("login"))

        if not check_password_hash(user["password"], password):
            flash("Invalid login details.", "danger")
            return redirect(url_for("login"))

        session.clear()

        session["user_id"] = user["id"]
        session["school_id"] = user["school_id"]
        session["role"] = user["role"]
        session["full_name"] = user["full_name"]
        session["username"] = user["username"]

        # Branding for all roles
        session["school_name"] = "EduTrack"
        session["logo_url"] = ""

        if user["role"] == "super_admin":
            session["school_name"] = "EduTrack Super Admin"
        elif user["school_id"]:
            school = fetch_one("""
                SELECT school_name, logo_url
                FROM schools
                WHERE id = ?
            """, (user["school_id"],))

            if school:
                session["school_name"] = school["school_name"]
                session["logo_url"] = row_get(school, "logo_url", "") or ""

        if user["role"] == "parent":
            return redirect(url_for("parent_dashboard"))

        if user["role"] == "teacher":
            return redirect(url_for("teacher_dashboard"))

        return redirect(url_for("dashboard"))

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
    school_id = session.get("school_id")
    role = session.get("role")

    search = request.args.get("search", "").strip()
    action_filter = request.args.get("action", "").strip()
    role_filter = request.args.get("role", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    query = """
        SELECT *
        FROM audit_logs
        WHERE 1=1
    """
    params = []

    if role != "super_admin":
        query += " AND school_id = ?"
        params.append(school_id)

        query += " AND role != ?"
        params.append("super_admin")

    if search:
        query += """
            AND (
                username LIKE ?
                OR action LIKE ?
                OR table_name LIKE ?
                OR details LIKE ?
            )
        """
        like = f"%{search}%"
        params.extend([like, like, like, like])

    if action_filter:
        query += " AND action LIKE ?"
        params.append(f"%{action_filter}%")

    if role_filter:
        query += " AND role = ?"
        params.append(role_filter)

    if start_date:
        query += " AND DATE(created_at) >= ?"
        params.append(start_date)

    if end_date:
        query += " AND DATE(created_at) <= ?"
        params.append(end_date)

    query += " ORDER BY created_at DESC LIMIT 300"

    logs = fetch_all(query, tuple(params))

    return render_template(
        "audit_logs.html",
        logs=logs,
        search=search,
        action_filter=action_filter,
        role_filter=role_filter,
        start_date=start_date,
        end_date=end_date
    )

@app.route("/edit_timetable_entry/<int:timetable_id>", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def edit_timetable_entry(timetable_id):

    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        entry = fetch_one("""
            SELECT *
            FROM timetables
            WHERE id = ?
        """, (timetable_id,))
    else:
        entry = fetch_one("""
            SELECT *
            FROM timetables
            WHERE id = ?
              AND school_id = ?
        """, (timetable_id, school_id))

    if not entry:
        flash("Timetable entry not found.", "danger")
        return redirect(url_for("timetable", view="master"))

    teachers = fetch_all("""
        SELECT id, full_name
        FROM teachers
        WHERE school_id = ?
        ORDER BY full_name
    """, (entry["school_id"],))

    if request.method == "POST":

        day_of_week = request.form.get("day_of_week")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        subject = request.form.get("subject")
        class_name = request.form.get("class_name")
        teacher_id = request.form.get("teacher_id")
        room = request.form.get("room")

        execute_commit("""
            UPDATE timetables
            SET day_of_week = ?,
                start_time = ?,
                end_time = ?,
                subject = ?,
                class_name = ?,
                teacher_id = ?,
                room = ?
            WHERE id = ?
        """, (
            day_of_week,
            start_time,
            end_time,
            subject,
            class_name,
            teacher_id if teacher_id else None,
            room,
            timetable_id
        ))

        flash("Timetable updated successfully.", "success")
        return redirect(url_for("timetable", view="master"))

    return render_template(
        "edit_timetable_entry.html",
        entry=entry,
        teachers=teachers
    )

@app.route("/fix_audit_table")
@login_required
@roles_required("super_admin")
def fix_audit_table():
    run_audit_migration()
    return "Audit table created successfully."

@app.route("/export_students_csv")
@login_required
@roles_required("school_admin", "super_admin")
def export_students_csv():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        students = fetch_all("""
            SELECT student_number, first_name, last_name, gender, class_name, current_status,
                   guardian1_name, guardian1_phone, guardian1_email
            FROM students
            ORDER BY class_name, first_name, last_name
        """)
    else:
        students = fetch_all("""
            SELECT student_number, first_name, last_name, gender, class_name, current_status,
                   guardian1_name, guardian1_phone, guardian1_email
            FROM students
            WHERE school_id = ?
            ORDER BY class_name, first_name, last_name
        """, (school_id,))

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Student Number", "First Name", "Last Name", "Gender", "Class",
        "Status", "Guardian", "Guardian Phone", "Guardian Email"
    ])

    for s in students:
        writer.writerow([
            s["student_number"],
            s["first_name"],
            s["last_name"],
            s["gender"],
            s["class_name"],
            s["current_status"],
            s["guardian1_name"],
            s["guardian1_phone"],
            s["guardian1_email"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=students_export.csv"}
    )


@app.route("/export_fees_csv")
@login_required
@roles_required("school_admin", "super_admin")
def export_fees_csv():
    school_id = session.get("school_id")
    role = session.get("role")

    query = """
        SELECT s.student_number, s.first_name, s.last_name, s.class_name,
               f.term_name, f.amount, f.paid_amount, f.balance, f.status, f.due_date
        FROM fees f
        JOIN students s ON f.student_id = s.id
    """
    params = []

    if role != "super_admin":
        query += " WHERE f.school_id = ?"
        params.append(school_id)

    query += " ORDER BY s.class_name, s.first_name, s.last_name, f.term_name"

    fees = fetch_all(query, tuple(params))

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Student Number", "First Name", "Last Name", "Class", "Term",
        "Total Fee", "Paid", "Balance", "Status", "Due Date"
    ])

    for f in fees:
        writer.writerow([
            f["student_number"],
            f["first_name"],
            f["last_name"],
            f["class_name"],
            f["term_name"],
            f["amount"],
            f["paid_amount"],
            f["balance"],
            f["status"],
            f["due_date"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=fees_export.csv"}
    )


@app.route("/export_results_csv")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def export_results_csv():
    school_id = session.get("school_id")
    role = session.get("role")

    query = """
        SELECT s.student_number, s.first_name, s.last_name,
               r.class_name, r.subject, r.term, r.marks, r.grade
        FROM results r
        JOIN students s ON r.student_id = s.id
    """
    params = []

    if role != "super_admin":
        query += " WHERE r.school_id = ?"
        params.append(school_id)

    query += " ORDER BY r.class_name, s.first_name, s.last_name, r.subject"

    results = fetch_all(query, tuple(params))

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Student Number", "First Name", "Last Name", "Class",
        "Subject", "Term", "Marks", "Grade"
    ])

    for r in results:
        writer.writerow([
            r["student_number"],
            r["first_name"],
            r["last_name"],
            r["class_name"],
            r["subject"],
            r["term"],
            r["marks"],
            r["grade"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=results_export.csv"}
    )


@app.route("/export_cashbook_csv")
@login_required
@roles_required("school_admin", "super_admin")
def export_cashbook_csv():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        entries = fetch_all("""
            SELECT entry_date, entry_type, category, description, amount,
                   payment_method, reference_number, created_by
            FROM cashbook
            ORDER BY entry_date DESC, id DESC
        """)
    else:
        entries = fetch_all("""
            SELECT entry_date, entry_type, category, description, amount,
                   payment_method, reference_number, created_by
            FROM cashbook
            WHERE school_id = ?
            ORDER BY entry_date DESC, id DESC
        """, (school_id,))

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Date", "Type", "Category", "Description", "Amount",
        "Payment Method", "Reference", "Recorded By"
    ])

    for e in entries:
        writer.writerow([
            e["entry_date"],
            e["entry_type"],
            e["category"],
            e["description"],
            e["amount"],
            e["payment_method"],
            e["reference_number"],
            e["created_by"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=cashbook_export.csv"}
    )


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
        teacher_list = fetch_all("""
            SELECT t.*, COALESCE(u.is_active, 1) AS is_active
            FROM teachers t
            LEFT JOIN users u ON t.user_id = u.id
            ORDER BY t.full_name
        """)
    else:
        teacher_list = fetch_all("""
            SELECT t.*, COALESCE(u.is_active, 1) AS is_active
            FROM teachers t
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.school_id = ?
            ORDER BY t.full_name
        """, (school_id,))

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

    selected_school_id = request.args.get("school_id") or school_id

    schools = []
    if role == "super_admin":
        schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    if request.method == "POST":
        if role == "super_admin":
            selected_school_id = request.form.get("school_id")

        teacher_id = request.form.get("teacher_id")
        class_name = request.form.get("class_name")
        subject = request.form.get("subject")

        if not selected_school_id or not teacher_id or not class_name or not subject:
            flash("School, teacher, class, and subject are required.", "danger")
            return redirect(url_for("assign_teacher", school_id=selected_school_id))

        teacher = fetch_one(
            "SELECT * FROM teachers WHERE id = ? AND school_id = ?",
            (teacher_id, selected_school_id)
        )

        if not teacher:
            flash("Invalid teacher selected for this school.", "danger")
            return redirect(url_for("assign_teacher", school_id=selected_school_id))

        existing = fetch_one("""
            SELECT *
            FROM teacher_assignments
            WHERE school_id = ?
              AND teacher_id = ?
              AND class_name = ?
              AND subject = ?
        """, (selected_school_id, teacher_id, class_name, subject))

        if existing:
            flash("This teacher is already assigned to that class and subject.", "warning")
            return redirect(url_for("assign_teacher", school_id=selected_school_id))

        execute_commit("""
            INSERT INTO teacher_assignments (school_id, teacher_id, class_name, subject)
            VALUES (?, ?, ?, ?)
        """, (selected_school_id, teacher_id, class_name, subject))
        log_audit(
            "Assigned teacher",
            "teacher_assignments",
            None,
            f"Assigned teacher ID {teacher_id} to {class_name} for {subject}"
)
        flash("Teacher assigned successfully.", "success")
        return redirect(url_for("assign_teacher", school_id=selected_school_id))

    teachers_list = []
    class_options = []
    subjects_list = []
    assignments_list = []

    if selected_school_id:
        teachers_list = fetch_all("""
            SELECT *
            FROM teachers
            WHERE school_id = ?
            ORDER BY full_name
        """, (selected_school_id,))

        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM school_classes
            WHERE school_id = ?
            ORDER BY class_name
        """, (selected_school_id,))

        class_options = [row["class_name"] for row in class_rows]

        subject_rows = fetch_all("""
            SELECT subject_name
            FROM subjects
            WHERE school_id = ?
            ORDER BY subject_name
        """, (selected_school_id,))

        subjects_list = [row["subject_name"] for row in subject_rows]

        assignments_list = fetch_all("""
            SELECT ta.*, t.full_name
            FROM teacher_assignments ta
            JOIN teachers t ON ta.teacher_id = t.id
            WHERE ta.school_id = ?
            ORDER BY t.full_name, ta.class_name, ta.subject
        """, (selected_school_id,))

    return render_template(
        "assign_teacher.html",
        schools=schools,
        selected_school_id=str(selected_school_id) if selected_school_id else "",
        teachers=teachers_list,
        class_options=class_options,
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
        SELECT *
        FROM teachers
        WHERE user_id = ?
          AND school_id = ?
        LIMIT 1
    """, (user_id, school_id))

    assignments_list = []
    timetable_rows = []
    assigned_classes = []
    assigned_subjects = []
    attendance_classes = []

    if teacher:
        teacher_id = teacher["id"]

        # Classes/subjects teacher teaches
        assignments_list = fetch_all("""
            SELECT *
            FROM teacher_assignments
            WHERE teacher_id = ?
              AND school_id = ?
            ORDER BY class_name, subject
        """, (teacher_id, school_id))

        assigned_classes = sorted(list(set([
            a["class_name"] for a in assignments_list if a["class_name"]
        ])))

        assigned_subjects = sorted(list(set([
            a["subject"] for a in assignments_list if a["subject"]
        ])))

        # ONLY official class-teacher classes for attendance
        class_teacher_rows = fetch_all("""
            SELECT class_name
            FROM school_classes
            WHERE class_teacher_id = ?
              AND school_id = ?
            ORDER BY class_name
        """, (teacher_id, school_id))

        attendance_classes = [
            row["class_name"] for row in class_teacher_rows if row["class_name"]
        ]

        # Timetable can still show all lessons teacher teaches
        timetable_rows = fetch_all("""
            SELECT *
            FROM timetables
            WHERE teacher_id = ?
              AND school_id = ?
            ORDER BY day_of_week, start_time
        """, (teacher_id, school_id))

    return render_template(
        "teacher_dashboard.html",
        teacher=teacher,
        assignments=assignments_list,
        timetable_rows=timetable_rows,
        assigned_classes=assigned_classes,
        assigned_subjects=assigned_subjects,
        attendance_classes=attendance_classes
    )
@app.route("/edit_teacher/<int:teacher_id>")
@login_required
@roles_required("school_admin", "super_admin")
def edit_teacher(teacher_id):

    school_id = session.get("school_id")

    teacher = fetch_one("""
        SELECT *
        FROM teachers
        WHERE id = ?
          AND school_id = ?
    """, (teacher_id, school_id))

    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for("teachers"))

    return render_template(
        "edit_teacher.html",
        teacher=teacher
    )
@app.route("/update_teacher/<int:teacher_id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def update_teacher(teacher_id):
    school_id = session.get("school_id")
    role = session.get("role")

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()

    if role == "super_admin":
        teacher = fetch_one("SELECT * FROM teachers WHERE id = ?", (teacher_id,))
    else:
        teacher = fetch_one(
            "SELECT * FROM teachers WHERE id = ? AND school_id = ?",
            (teacher_id, school_id)
        )

    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for("teachers"))

    if role == "super_admin":
        execute_commit("""
            UPDATE teachers
            SET full_name = ?, email = ?, phone = ?
            WHERE id = ?
        """, (full_name, email, phone, teacher_id))
    else:
        execute_commit("""
            UPDATE teachers
            SET full_name = ?, email = ?, phone = ?
            WHERE id = ? AND school_id = ?
        """, (full_name, email, phone, teacher_id, school_id))

    log_audit(
        "Updated teacher",
        "teachers",
        teacher_id,
        f"Updated teacher {full_name}"
    )

    flash("Teacher updated successfully.", "success")
    return redirect(url_for("teachers"))
@app.route("/deactivate_teacher/<int:teacher_id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def deactivate_teacher(teacher_id):

    school_id = session.get("school_id")

    teacher = fetch_one("""
        SELECT *
        FROM teachers
        WHERE id = ?
          AND school_id = ?
    """, (teacher_id, school_id))

    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for("teachers"))

    if teacher.get("user_id"):

        execute_commit("""
            UPDATE users
            SET is_active = 0
            WHERE id = ?
        """, (teacher["user_id"],))

    log_audit(
        "Deactivated teacher",
        "teachers",
        teacher_id,
        f"Deactivated teacher {teacher['full_name']}"
    )

    flash("Teacher deactivated successfully.", "success")

    return redirect(url_for("teachers"))
@app.route("/activate_teacher/<int:teacher_id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def activate_teacher(teacher_id):

    school_id = session.get("school_id")

    teacher = fetch_one("""
        SELECT *
        FROM teachers
        WHERE id = ?
          AND school_id = ?
    """, (teacher_id, school_id))

    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for("teachers"))

    if teacher.get("user_id"):

        execute_commit("""
            UPDATE users
            SET is_active = 1
            WHERE id = ?
        """, (teacher["user_id"],))

    log_audit(
        "Activated teacher",
        "teachers",
        teacher_id,
        f"Activated teacher {teacher['full_name']}"
    )

    flash("Teacher activated successfully.", "success")

    return redirect(url_for("teachers"))

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
    log_audit(
        "Added result",
        "results",
        None,
        f"Added result for student ID {student_id}, {subject}, {term}, marks {marks}"
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
    user_id = session.get("user_id")

    selected_class = request.args.get("class_name", "").strip()
    students_list = []
    class_options = []

    # =====================================================
    # TEACHER VIEW
    # =====================================================
    if role == "teacher":
        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE user_id = ? AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if not teacher:
            flash("No teacher profile is linked to this account.", "danger")
            return render_template(
                "attendance.html",
                class_options=[],
                selected_class="",
                students=[],
                today=datetime.now().strftime("%Y-%m-%d")
            )

        # Only classes where this teacher is the official class teacher
        class_teacher_rows = fetch_all("""
            SELECT class_name
            FROM school_classes
            WHERE class_teacher_id = ?
            AND school_id = ?
            ORDER BY class_name
        """, (teacher["id"], school_id))

        class_options = [row["class_name"] for row in class_teacher_rows]

        if not selected_class and len(class_options) == 1:
            selected_class = class_options[0]

        if selected_class and selected_class in class_options:
            students_list = fetch_all("""
                SELECT *
                FROM students
                WHERE school_id = ?
                AND class_name = ?
                AND COALESCE(current_status, 'Active') = 'Active'
                ORDER BY first_name, last_name
            """, (school_id, selected_class))
        else:
            students_list = []
    # =====================================================
    # SUPER ADMIN VIEW
    # =====================================================
    elif role == "super_admin":
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM school_classes
            ORDER BY class_name
        """)

        class_options = [row["class_name"] for row in class_rows] or CLASS_OPTIONS

        if selected_class:
            students_list = fetch_all("""
                SELECT *
                FROM students
                WHERE class_name = ?
                  AND COALESCE(current_status, 'Active') = 'Active'
                ORDER BY first_name, last_name
            """, (selected_class,))

    # =====================================================
    # SCHOOL ADMIN VIEW
    # =====================================================
    else:
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM school_classes
            WHERE school_id = ?
            ORDER BY class_name
        """, (school_id,))

        class_options = [row["class_name"] for row in class_rows] or CLASS_OPTIONS

        if selected_class:
            students_list = fetch_all("""
                SELECT *
                FROM students
                WHERE school_id = ?
                  AND class_name = ?
                  AND COALESCE(current_status, 'Active') = 'Active'
                ORDER BY first_name, last_name
            """, (school_id, selected_class))

    return render_template(
        "attendance.html",
        class_options=class_options,
        selected_class=selected_class,
        students=students_list,
        today=datetime.now().strftime("%Y-%m-%d")
    )
    
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

    saved_count = 0
    updated_count = 0

    try:
        for student_id in student_ids:
            if role != "super_admin":
                student = fetch_one(
                    "SELECT * FROM students WHERE id = ? AND school_id = ?",
                    (student_id, school_id)
                )
                if not student:
                    continue
            else:
                student = fetch_one(
                    "SELECT * FROM students WHERE id = ?",
                    (student_id,)
                )
                if not student:
                    continue

                school_id = student["school_id"]

            status = request.form.get(f"status_{student_id}")

            existing = fetch_one("""
                SELECT id
                FROM attendance
                WHERE student_id = ?
                  AND class_name = ?
                  AND date = ?
            """, (student_id, class_name, date))

            if existing:
                cursor.execute(
                    convert_query("""
                        UPDATE attendance
                        SET status = ?
                        WHERE id = ?
                    """),
                    (status, existing["id"])
                )
                updated_count += 1
            else:
                cursor.execute(
                    convert_query("""
                        INSERT INTO attendance (
                            school_id, student_id, class_name, date, status
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """),
                    (
                        school_id,
                        student_id,
                        class_name,
                        date,
                        status
                    )
                )
                saved_count += 1

        conn.commit()

        log_audit(
            "Saved attendance",
            "attendance",
            None,
            f"Saved attendance for {class_name} on {date}. New: {saved_count}, Updated: {updated_count}"
        )

        if saved_count > 0 and updated_count > 0:
            flash(f"Attendance saved. New records: {saved_count}, updated records: {updated_count}.", "success")
        elif updated_count > 0:
            flash("Attendance was already marked for this class/date, so the records were updated instead of duplicated.", "success")
        else:
            flash("Attendance saved successfully.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Error saving attendance: {str(e)}", "danger")

    finally:
        conn.close()

    return redirect(url_for("attendance", class_name=class_name))
@app.route("/debug_audit")
@login_required
@roles_required("super_admin")
def debug_audit():
    rows = fetch_all("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 10")
    return "<pre>" + str(rows) + "</pre>"

@app.route("/attendance_records")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def attendance_records():
    school_id = session.get("school_id")
    role = session.get("role")

    selected_class = request.args.get("class_name", "").strip()
    selected_date = request.args.get("date", "").strip()

    query = """
        SELECT 
            a.*,
            s.first_name,
            s.last_name,
            s.student_number,
            s.class_name AS student_class
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE 1=1
    """
    params = []

    if role != "super_admin":
        query += " AND a.school_id = ?"
        params.append(school_id)

    if selected_class:
        query += " AND a.class_name = ?"
        params.append(selected_class)

    if selected_date:
        query += " AND a.date = ?"
        params.append(selected_date)

    query += " ORDER BY a.date DESC, a.class_name, s.first_name, s.last_name"

    attendance_list = fetch_all(query, tuple(params))

    total_records = len(attendance_list)
    present_count = sum(1 for a in attendance_list if a["status"] == "Present")
    absent_count = sum(1 for a in attendance_list if a["status"] == "Absent")
    late_count = sum(1 for a in attendance_list if a["status"] == "Late")

    attendance_percentage = 0
    absent_percentage = 0
    late_percentage = 0

    if total_records > 0:
        attendance_percentage = round((present_count / total_records) * 100, 1)
        absent_percentage = round((absent_count / total_records) * 100, 1)
        late_percentage = round((late_count / total_records) * 100, 1)

    if role == "super_admin":
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM attendance
            WHERE class_name IS NOT NULL
              AND class_name != ''
            ORDER BY class_name
        """)
    else:
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM attendance
            WHERE school_id = ?
              AND class_name IS NOT NULL
              AND class_name != ''
            ORDER BY class_name
        """, (school_id,))

    class_options = [row["class_name"] for row in class_rows]

    return render_template(
        "attendance_records.html",
        attendance_records=attendance_list,
        class_options=class_options,
        selected_class=selected_class,
        selected_date=selected_date,
        total_records=total_records,
        present_count=present_count,
        absent_count=absent_count,
        late_count=late_count,
        attendance_percentage=attendance_percentage,
        absent_percentage=absent_percentage,
        late_percentage=late_percentage
    )

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

    # Get linked student
    student = fetch_one("""
        SELECT s.*
        FROM students s
        JOIN guardians g ON s.id = g.student_id
        WHERE g.parent_user_id = ?
          AND s.school_id = ?
        LIMIT 1
    """, (user_id, school_id))

    # If no student linked, still load page safely
    if not student:
        return render_template(
            "parent_dashboard.html",
            student=None,
            fee_summary={
                "total_amount": 0,
                "total_paid": 0,
                "total_balance": 0
            },
            notices=[]
        )

    # Fee summary
    fee_summary = fetch_one("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_amount,
            COALESCE(SUM(paid_amount), 0) AS total_paid,
            COALESCE(SUM(balance), 0) AS total_balance
        FROM fees
        WHERE student_id = ?
          AND school_id = ?
    """, (student["id"], school_id))

    # Safe notices (no crash even if table missing)
    notices = []
    try:
        notices = fetch_all("""
    SELECT *
    FROM notices
    WHERE (school_id = ? OR school_id IS NULL)
      AND (class_name = ? OR class_name IS NULL OR class_name = '')
    ORDER BY date DESC, id DESC
    LIMIT 5
""", (school_id, student["class_name"]))
    except Exception:
        notices = []

    return render_template(
        "parent_dashboard.html",
        student=student,
        fee_summary=fee_summary,
        notices=notices
    )

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

@app.route("/parent_fees")
@login_required
@roles_required("parent")
def parent_fees():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    fee_records = fetch_all("""
        SELECT f.*, s.first_name, s.last_name, s.class_name, s.student_number
        FROM fees f
        JOIN students s ON f.student_id = s.id
        JOIN guardians g ON s.id = g.student_id
        WHERE g.parent_user_id = ?
          AND f.school_id = ?
        ORDER BY f.term_name
    """, (user_id, school_id))

    return render_template("parent_fees.html", fee_records=fee_records)

# =========================================================
# NOTICES
# =========================================================

@app.route("/notices")
@login_required
@roles_required("school_admin", "super_admin")
def notices():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        notice_list = fetch_all("""
            SELECT n.*, s.school_name
            FROM notices n
            LEFT JOIN schools s ON n.school_id = s.id
            ORDER BY n.date DESC, n.id DESC
        """)
    else:
        notice_list = fetch_all("""
            SELECT *
            FROM notices
            WHERE school_id = ?
            ORDER BY date DESC, id DESC
        """, (school_id,))

    return render_template("notices.html", notices=notice_list)


@app.route("/add_notice", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def add_notice():
    school_id = session.get("school_id")
    role = session.get("role")

    # Super admin can choose school
    schools = []
    if role == "super_admin":
        schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    # Get classes for dropdown
    classes = fetch_all("""
        SELECT DISTINCT class_name
        FROM school_classes
        WHERE school_id = ?
        ORDER BY class_name
    """, (school_id,))

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        class_name = request.form.get("class_name")
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        created_by = session.get("full_name")
        today = datetime.now().strftime("%Y-%m-%d")

        if not title or not message:
            flash("Title and message are required.", "danger")
            return redirect(url_for("add_notice"))

        execute_commit("""
            INSERT INTO notices (school_id, class_name, title, message, date, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (school_id, class_name, title, message, today, created_by))

        flash("Notice posted successfully.", "success")
        return redirect(url_for("notices"))

    return render_template(
        "add_notice.html",
        schools=schools,
        classes=classes
    )

@app.route("/edit_notice/<int:notice_id>", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def edit_notice(notice_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        notice = fetch_one("SELECT * FROM notices WHERE id = ?", (notice_id,))
    else:
        notice = fetch_one(
            "SELECT * FROM notices WHERE id = ? AND school_id = ?",
            (notice_id, school_id)
        )

    if not notice:
        flash("Notice not found or access denied.", "danger")
        return redirect(url_for("notices"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()

        if not title or not message:
            flash("Title and message are required.", "danger")
            return redirect(url_for("edit_notice", notice_id=notice_id))

        execute_commit("""
            UPDATE notices
            SET title = ?, message = ?
            WHERE id = ?
        """, (title, message, notice_id))

        log_audit(
            "Edited notice",
            "notices",
            notice_id,
            f"Updated notice: {title}"
        )

        flash("Notice updated successfully.", "success")
        return redirect(url_for("notices"))

    return render_template("edit_notice.html", notice=notice)


@app.route("/delete_notice/<int:notice_id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def delete_notice(notice_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        notice = fetch_one("SELECT * FROM notices WHERE id = ?", (notice_id,))
    else:
        notice = fetch_one(
            "SELECT * FROM notices WHERE id = ? AND school_id = ?",
            (notice_id, school_id)
        )

    if not notice:
        flash("Notice not found or access denied.", "danger")
        return redirect(url_for("notices"))

    execute_commit("DELETE FROM notices WHERE id = ?", (notice_id,))

    log_audit(
        "Deleted notice",
        "notices",
        notice_id,
        f"Deleted notice: {notice['title']}"
    )

    flash("Notice deleted successfully.", "success")
    return redirect(url_for("notices"))  
# =========================================================
# TIMETABLE
# =========================================================
@app.route("/timetable")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def timetable():
    school_id = session.get("school_id")
    role = session.get("role")
    user_id = session.get("user_id")

    view_mode = request.args.get("view", "class").strip()
    selected_class = request.args.get("class_name", "").strip()
    selected_teacher = request.args.get("teacher_id", "").strip()

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    timetable_rows = []

    # Get classes
    if role == "super_admin":
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM timetables
            WHERE class_name IS NOT NULL AND class_name != ''
            ORDER BY class_name
        """)
        teachers = fetch_all("""
            SELECT id, full_name
            FROM teachers
            ORDER BY full_name
        """)
    else:
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM timetables
            WHERE school_id = ?
              AND class_name IS NOT NULL AND class_name != ''
            ORDER BY class_name
        """, (school_id,))

        teachers = fetch_all("""
            SELECT id, full_name
            FROM teachers
            WHERE school_id = ?
            ORDER BY full_name
        """, (school_id,))

    class_options = [row["class_name"] for row in class_rows]

    # Teacher logged in: force teacher view
    if role == "teacher":
        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE user_id = ?
              AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if teacher:
            selected_teacher = str(teacher["id"])
            view_mode = "teacher"

    # CLASS VIEW
    if view_mode == "class" and selected_class:
        if role == "super_admin":
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                WHERE LOWER(TRIM(t.class_name)) = LOWER(TRIM(?))
                ORDER BY t.day_of_week, t.start_time
            """, (selected_class,))
        else:
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                WHERE t.school_id = ?
                  AND LOWER(TRIM(t.class_name)) = LOWER(TRIM(?))
                ORDER BY t.day_of_week, t.start_time
            """, (school_id, selected_class))

    # TEACHER VIEW
    elif view_mode == "teacher" and selected_teacher:
        if role == "super_admin":
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                WHERE t.teacher_id = ?
                ORDER BY t.day_of_week, t.start_time
            """, (selected_teacher,))
        else:
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                WHERE t.school_id = ?
                  AND t.teacher_id = ?
                ORDER BY t.day_of_week, t.start_time
            """, (school_id, selected_teacher))

    # MASTER VIEW
    elif view_mode == "master":
        if role == "super_admin":
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                ORDER BY t.class_name, t.day_of_week, t.start_time
            """)
        else:
            timetable_rows = fetch_all("""
                SELECT t.*, tr.full_name
                FROM timetables t
                LEFT JOIN teachers tr ON t.teacher_id = tr.id
                WHERE t.school_id = ?
                ORDER BY t.class_name, t.day_of_week, t.start_time
            """, (school_id,))

    return render_template(
        "timetable.html",
        view_mode=view_mode,
        class_options=class_options,
        teachers=teachers,
        selected_class=selected_class,
        selected_teacher=selected_teacher,
        timetable_rows=timetable_rows,
        days=days
    )

@app.route("/import_teacher_assignments", methods=["GET", "POST"])
@login_required
@roles_required("super_admin", "school_admin")
def import_teacher_assignments():
    school_id = session.get("school_id")
    role = session.get("role")

    schools = fetch_all("SELECT * FROM schools ORDER BY school_name") if role == "super_admin" else []

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        file = request.files.get("assignment_file")

        if not school_id or not file or not file.filename:
            flash("School and Excel file are required.", "danger")
            return redirect(url_for("import_teacher_assignments"))

        try:
            df = pd.read_excel(file)

            required_columns = ["teacher_name", "class_name", "subject"]
            missing = [c for c in required_columns if c not in df.columns]

            if missing:
                flash(f"Missing columns: {', '.join(missing)}", "danger")
                return redirect(url_for("import_teacher_assignments"))

            imported = 0
            skipped = 0

            conn = get_db()
            cursor = conn.cursor()

            try:
                for _, row in df.iterrows():
                    teacher_name = str(row.get("teacher_name", "")).strip()
                    class_name = str(row.get("class_name", "")).strip()
                    subject = str(row.get("subject", "")).strip()

                    if not teacher_name or not class_name or not subject:
                        skipped += 1
                        continue

                    cursor.execute(convert_query("""
                        SELECT id
                        FROM teachers
                        WHERE school_id = ?
                          AND LOWER(TRIM(full_name)) = LOWER(TRIM(?))
                        LIMIT 1
                    """), (school_id, teacher_name))

                    teacher = cursor.fetchone()

                    if not teacher:
                        skipped += 1
                        continue

                    teacher_id = teacher["id"]

                    cursor.execute(convert_query("""
                        SELECT id
                        FROM teacher_assignments
                        WHERE school_id = ?
                          AND teacher_id = ?
                          AND LOWER(TRIM(class_name)) = LOWER(TRIM(?))
                          AND LOWER(TRIM(subject)) = LOWER(TRIM(?))
                        LIMIT 1
                    """), (school_id, teacher_id, class_name, subject))

                    existing = cursor.fetchone()

                    if existing:
                        skipped += 1
                        continue

                    cursor.execute(convert_query("""
                        INSERT INTO teacher_assignments (
                            school_id, teacher_id, class_name, subject
                        )
                        VALUES (?, ?, ?, ?)
                    """), (school_id, teacher_id, class_name, subject))

                    # Also update matching timetable rows with this teacher
                    cursor.execute(convert_query("""
                        UPDATE timetables
                        SET teacher_id = ?
                        WHERE school_id = ?
                          AND LOWER(TRIM(class_name)) = LOWER(TRIM(?))
                          AND LOWER(TRIM(subject)) = LOWER(TRIM(?))
                          AND teacher_id IS NULL
                    """), (teacher_id, school_id, class_name, subject))

                    imported += 1

                conn.commit()

            except Exception:
                conn.rollback()
                raise

            finally:
                conn.close()

            flash(f"Teacher assignment import complete. Imported: {imported}, Skipped: {skipped}", "success")
            return redirect(url_for("assign_teacher"))

        except Exception as e:
            flash(f"Import failed: {str(e)}", "danger")
            return redirect(url_for("import_teacher_assignments"))

    return render_template("import_teacher_assignments.html", schools=schools)
@app.route("/teacher_assignments")
@login_required
@roles_required("school_admin", "super_admin")
def teacher_assignments_page():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        assignments = fetch_all("""
            SELECT ta.*, t.full_name, s.school_name
            FROM teacher_assignments ta
            JOIN teachers t ON ta.teacher_id = t.id
            LEFT JOIN schools s ON ta.school_id = s.id
            ORDER BY s.school_name, t.full_name, ta.class_name, ta.subject
        """)
    else:
        assignments = fetch_all("""
            SELECT ta.*, t.full_name
            FROM teacher_assignments ta
            JOIN teachers t ON ta.teacher_id = t.id
            WHERE ta.school_id = ?
            ORDER BY t.full_name, ta.class_name, ta.subject
        """, (school_id,))

    return render_template("teacher_assignments.html", assignments=assignments)

@app.route("/edit_teacher_assignment/<int:assignment_id>", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def edit_teacher_assignment(assignment_id):
    role = session.get("role")

    assignment = fetch_one("""
        SELECT *
        FROM teacher_assignments
        WHERE id = ?
    """, (assignment_id,))

    if not assignment:
        flash("Assignment not found.", "danger")
        return redirect(url_for("teacher_assignments_page"))

    school_id = assignment["school_id"]

    if role != "super_admin" and school_id != session.get("school_id"):
        flash("You are not allowed to edit this assignment.", "danger")
        return redirect(url_for("teacher_assignments_page"))

    teachers = fetch_all("""
        SELECT id, full_name
        FROM teachers
        WHERE school_id = ?
        ORDER BY full_name
    """, (school_id,))

    classes = fetch_all("""
        SELECT DISTINCT class_name
        FROM school_classes
        WHERE school_id = ?
        ORDER BY class_name
    """, (school_id,))

    subjects = fetch_all("""
        SELECT subject_name
        FROM subjects
        WHERE school_id = ?
        ORDER BY subject_name
    """, (school_id,))

    if request.method == "POST":
        teacher_id = request.form.get("teacher_id")
        class_name = request.form.get("class_name")
        subject = request.form.get("subject")

        execute_commit("""
            UPDATE timetables
            SET teacher_id = NULL
            WHERE school_id = ?
              AND teacher_id = ?
              AND class_name = ?
              AND subject = ?
        """, (
            school_id,
            assignment["teacher_id"],
            assignment["class_name"],
            assignment["subject"]
        ))

        execute_commit("""
            UPDATE teacher_assignments
            SET teacher_id = ?, class_name = ?, subject = ?
            WHERE id = ?
        """, (teacher_id, class_name, subject, assignment_id))

        execute_commit("""
            UPDATE timetables
            SET teacher_id = ?
            WHERE school_id = ?
              AND class_name = ?
              AND subject = ?
        """, (teacher_id, school_id, class_name, subject))

        flash("Teacher assignment updated successfully.", "success")
        return redirect(url_for("teacher_assignments_page"))

    return render_template(
        "edit_teacher_assignment.html",
        assignment=assignment,
        teachers=teachers,
        classes=classes,
        subjects=subjects
    )
@app.route("/delete_teacher_assignment/<int:assignment_id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def delete_teacher_assignment(assignment_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        assignment = fetch_one("SELECT * FROM teacher_assignments WHERE id = ?", (assignment_id,))
    else:
        assignment = fetch_one("""
            SELECT *
            FROM teacher_assignments
            WHERE id = ? AND school_id = ?
        """, (assignment_id, school_id))

    if not assignment:
        flash("Teacher assignment not found.", "danger")
        return redirect(url_for("teacher_assignments_page"))

    execute_commit("""
        UPDATE timetables
        SET teacher_id = NULL
        WHERE school_id = ?
          AND LOWER(TRIM(class_name)) = LOWER(TRIM(?))
          AND LOWER(TRIM(subject)) = LOWER(TRIM(?))
    """, (
        assignment["school_id"],
        assignment["class_name"],
        assignment["subject"]
    ))

    execute_commit("DELETE FROM teacher_assignments WHERE id = ?", (assignment_id,))

    flash("Teacher assignment deleted successfully.", "success")
    return redirect(url_for("teacher_assignments_page"))

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
    user_id = session.get("user_id")

    # Extra teacher security:
    # Teacher can only open classes assigned to them or where they are class teacher.
    if role == "teacher":
        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE user_id = ?
              AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if not teacher:
            flash("No teacher profile linked to this account.", "danger")
            return redirect(url_for("teacher_dashboard"))

        allowed_class = fetch_one("""
            SELECT 1
            FROM teacher_assignments
            WHERE teacher_id = ?
              AND school_id = ?
              AND class_name = ?
            LIMIT 1
        """, (teacher["id"], school_id, class_name))

        class_teacher_class = fetch_one("""
            SELECT 1
            FROM school_classes
            WHERE class_teacher_id = ?
              AND school_id = ?
              AND class_name = ?
            LIMIT 1
        """, (teacher["id"], school_id, class_name))

        if not allowed_class and not class_teacher_class:
            flash("You are not allowed to view this class.", "danger")
            return redirect(url_for("teacher_dashboard"))

    # Students
    if role == "super_admin":
        students = fetch_all("""
            SELECT *
            FROM students
            WHERE class_name = ?
            ORDER BY first_name, last_name
        """, (class_name,))
    else:
        students = fetch_all("""
            SELECT *
            FROM students
            WHERE school_id = ?
              AND class_name = ?
            ORDER BY first_name, last_name
        """, (school_id, class_name))

    # Attendance summary
    if role == "super_admin":
        attendance_summary = fetch_one("""
            SELECT
                COUNT(*) AS total_records,
                COALESCE(SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END), 0) AS present_count,
                COALESCE(SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END), 0) AS absent_count
            FROM attendance
            WHERE class_name = ?
        """, (class_name,))
    else:
        attendance_summary = fetch_one("""
            SELECT
                COUNT(*) AS total_records,
                COALESCE(SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END), 0) AS present_count,
                COALESCE(SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END), 0) AS absent_count
            FROM attendance
            WHERE school_id = ?
              AND class_name = ?
        """, (school_id, class_name))

    # Fees summary: never expose to teachers
    fee_summary = None

    if role != "teacher":
        if role == "super_admin":
            fee_summary = fetch_one("""
                SELECT
                    COALESCE(SUM(f.amount), 0) AS total_fees,
                    COALESCE(SUM(f.paid_amount), 0) AS total_paid,
                    COALESCE(SUM(f.balance), 0) AS total_balance
                FROM fees f
                JOIN students s ON f.student_id = s.id
                WHERE s.class_name = ?
            """, (class_name,))
        else:
            fee_summary = fetch_one("""
                SELECT
                    COALESCE(SUM(f.amount), 0) AS total_fees,
                    COALESCE(SUM(f.paid_amount), 0) AS total_paid,
                    COALESCE(SUM(f.balance), 0) AS total_balance
                FROM fees f
                JOIN students s ON f.student_id = s.id
                WHERE f.school_id = ?
                  AND s.class_name = ?
            """, (school_id, class_name))

    # Results summary
    if role == "super_admin":
        results_summary = fetch_one("""
            SELECT
                COUNT(*) AS total_results,
                COALESCE(AVG(marks), 0) AS average_marks
            FROM results
            WHERE class_name = ?
        """, (class_name,))
    else:
        results_summary = fetch_one("""
            SELECT
                COUNT(*) AS total_results,
                COALESCE(AVG(marks), 0) AS average_marks
            FROM results
            WHERE school_id = ?
              AND class_name = ?
        """, (school_id, class_name))

    # Timetable rows
    if role == "super_admin":
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
                    ELSE 8
                END,
                t.start_time
        """, (class_name,))
    else:
        timetable_rows = fetch_all("""
            SELECT t.*, tr.full_name
            FROM timetables t
            LEFT JOIN teachers tr ON t.teacher_id = tr.id
            WHERE t.school_id = ?
              AND t.class_name = ?
            ORDER BY
                CASE t.day_of_week
                    WHEN 'Monday' THEN 1
                    WHEN 'Tuesday' THEN 2
                    WHEN 'Wednesday' THEN 3
                    WHEN 'Thursday' THEN 4
                    WHEN 'Friday' THEN 5
                    WHEN 'Saturday' THEN 6
                    WHEN 'Sunday' THEN 7
                    ELSE 8
                END,
                t.start_time
        """, (school_id, class_name))

    active_students = sum(
        1 for s in students
        if (s["current_status"] or "Active") == "Active"
    )

    inactive_students = len(students) - active_students

    return render_template(
        "class_students.html",
        class_name=class_name,
        students=students,
        total_students=len(students),
        active_students=active_students,
        inactive_students=inactive_students,
        attendance_summary=attendance_summary,
        fee_summary=fee_summary,
        results_summary=results_summary,
        timetable_rows=timetable_rows
    )

@app.route("/delete_class/<int:class_id>", methods=["POST"])
@login_required
@roles_required("super_admin")
def delete_class(class_id):
    class_row = fetch_one("SELECT * FROM school_classes WHERE id = ?", (class_id,))

    if not class_row:
        flash("Class not found.", "danger")
        return redirect(url_for("classes"))

    execute_commit("DELETE FROM school_classes WHERE id = ?", (class_id,))

    log_audit(
        "Deleted class",
        "school_classes",
        class_id,
        f"Deleted class {class_row['class_name']}"
    )

    flash("Class deleted successfully.", "success")
    return redirect(url_for("classes"))

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
        log_audit(
                "Added subject",
                "subjects",
                None,
                f"Added subject: {subject_name}"
)
        flash("Subject added successfully.", "success")
        return redirect(url_for("subjects"))

    return render_template("add_subject.html", schools=schools)

@app.route("/search")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def global_search():
    q = request.args.get("q", "").strip()
    school_id = session.get("school_id")
    role = session.get("role")

    students = []
    teachers = []

    if q:
        like = f"%{q}%"

        if role == "super_admin":
            students = fetch_all("""
                SELECT *
                FROM students
                WHERE first_name LIKE ?
                   OR last_name LIKE ?
                   OR student_number LIKE ?
                   OR class_name LIKE ?
                   OR guardian1_name LIKE ?
                   OR guardian1_phone LIKE ?
                ORDER BY class_name, first_name, last_name
                LIMIT 30
            """, (like, like, like, like, like, like))

            teachers = fetch_all("""
                SELECT *
                FROM teachers
                WHERE full_name LIKE ?
                   OR phone LIKE ?
                   OR email LIKE ?
                ORDER BY full_name
                LIMIT 20
            """, (like, like, like))

        else:
            students = fetch_all("""
                SELECT *
                FROM students
                WHERE school_id = ?
                  AND (
                    first_name LIKE ?
                    OR last_name LIKE ?
                    OR student_number LIKE ?
                    OR class_name LIKE ?
                    OR guardian1_name LIKE ?
                    OR guardian1_phone LIKE ?
                  )
                ORDER BY class_name, first_name, last_name
                LIMIT 30
            """, (school_id, like, like, like, like, like, like))

            teachers = fetch_all("""
                SELECT *
                FROM teachers
                WHERE school_id = ?
                  AND (
                    full_name LIKE ?
                    OR phone LIKE ?
                    OR email LIKE ?
                  )
                ORDER BY full_name
                LIMIT 20
            """, (school_id, like, like, like))

    return render_template(
        "global_search.html",
        q=q,
        students=students,
        teachers=teachers
    )
@app.route("/import_timetable", methods=["GET", "POST"])
@login_required
@roles_required("super_admin", "school_admin")
def import_timetable():
    school_id = session.get("school_id")
    role = session.get("role")

    schools = fetch_all("SELECT * FROM schools ORDER BY school_name") if role == "super_admin" else []

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        file = request.files.get("timetable_file")

        if not school_id or not file or not file.filename:
            flash("School and Excel file are required.", "danger")
            return redirect(url_for("import_timetable"))

        try:
            df = pd.read_excel(file)

            required_columns = [
                "class_name", "day_of_week", "start_time", "end_time",
                "subject", "teacher_name", "room"
            ]

            missing = [c for c in required_columns if c not in df.columns]
            if missing:
                flash(f"Missing columns: {', '.join(missing)}", "danger")
                return redirect(url_for("import_timetable"))

            imported = 0
            updated = 0
            skipped = 0

            conn = get_db()
            cursor = conn.cursor()

            try:
                for _, row in df.iterrows():
                    class_name = str(row.get("class_name", "")).strip()
                    day_of_week = str(row.get("day_of_week", "")).strip()
                    start_time = str(row.get("start_time", "")).strip()
                    end_time = str(row.get("end_time", "")).strip()
                    subject = str(row.get("subject", "")).strip()
                    teacher_name = str(row.get("teacher_name", "")).strip()
                    room = str(row.get("room", "")).strip()

                    if (
                        not class_name
                        or not day_of_week
                        or not start_time
                        or not end_time
                        or not subject
                    ):
                        skipped += 1
                        continue

                    teacher_id = None

                    if teacher_name:
                        cursor.execute(convert_query("""
                            SELECT id
                            FROM teachers
                            WHERE school_id = ?
                              AND LOWER(TRIM(full_name)) = LOWER(TRIM(?))
                            LIMIT 1
                        """), (school_id, teacher_name))

                        teacher = cursor.fetchone()

                        if teacher:
                            teacher_id = teacher["id"]

                    cursor.execute(convert_query("""
                        SELECT id
                        FROM timetables
                        WHERE school_id = ?
                          AND class_name = ?
                          AND day_of_week = ?
                          AND start_time = ?
                          AND end_time = ?
                        LIMIT 1
                    """), (
                        school_id,
                        class_name,
                        day_of_week,
                        start_time,
                        end_time
                    ))

                    existing = cursor.fetchone()

                    if existing:
                        cursor.execute(convert_query("""
                            UPDATE timetables
                            SET subject = ?,
                                teacher_id = ?,
                                room = ?
                            WHERE id = ?
                        """), (
                            subject,
                            teacher_id,
                            room,
                            existing["id"]
                        ))
                        updated += 1
                    else:
                        cursor.execute(convert_query("""
                            INSERT INTO timetables (
                                school_id,
                                class_name,
                                subject,
                                teacher_id,
                                day_of_week,
                                start_time,
                                end_time,
                                room
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """), (
                            school_id,
                            class_name,
                            subject,
                            teacher_id,
                            day_of_week,
                            start_time,
                            end_time,
                            room
                        ))
                        imported += 1

                conn.commit()

            except Exception:
                conn.rollback()
                raise

            finally:
                conn.close()

            flash(
                f"Timetable import complete. Imported: {imported}, Updated: {updated}, Skipped: {skipped}",
                "success"
            )
            return redirect(url_for("timetable"))

        except Exception as e:
            flash(f"Import failed: {str(e)}", "danger")
            return redirect(url_for("import_timetable"))

    return render_template("import_timetable.html", schools=schools)

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
        log_audit(
            "Added timetable entry",
            "timetables",
            None,
            f"Added {subject} for {class_name} on {day_of_week} from {start_time} to {end_time}"
)
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
@app.route("/assign_class_teacher", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def assign_class_teacher():
    school_id = session.get("school_id")
    role = session.get("role")

    selected_school_id = request.args.get("school_id") or school_id

    schools = []
    if role == "super_admin":
        schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    if request.method == "POST":
        if role == "super_admin":
            selected_school_id = request.form.get("school_id")
        else:
            selected_school_id = school_id

        class_id = request.form.get("class_id")
        teacher_id = request.form.get("teacher_id")

        if not selected_school_id or not class_id or not teacher_id:
            flash("School, class, and teacher are required.", "danger")
            return redirect(url_for("assign_class_teacher", school_id=selected_school_id))

        class_row = fetch_one("""
            SELECT *
            FROM school_classes
            WHERE id = ?
              AND school_id = ?
        """, (class_id, selected_school_id))

        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE id = ?
              AND school_id = ?
        """, (teacher_id, selected_school_id))

        if not class_row or not teacher:
            flash("Invalid class or teacher selected for this school.", "danger")
            return redirect(url_for("assign_class_teacher", school_id=selected_school_id))

        execute_commit("""
            UPDATE school_classes
            SET class_teacher_id = ?
            WHERE id = ?
              AND school_id = ?
        """, (teacher_id, class_id, selected_school_id))

        log_audit(
            "Assigned class teacher",
            "school_classes",
            class_id,
            f"Assigned {teacher['full_name']} as class teacher for {class_row['class_name']}"
        )

        flash("Class teacher assigned successfully.", "success")
        return redirect(url_for("assign_class_teacher", school_id=selected_school_id))

    teachers = []
    classes = []
    class_assignments = []

    if selected_school_id:
        teachers = fetch_all("""
            SELECT *
            FROM teachers
            WHERE school_id = ?
            ORDER BY full_name
        """, (selected_school_id,))

        classes = fetch_all("""
            SELECT *
            FROM school_classes
            WHERE school_id = ?
            ORDER BY class_name
        """, (selected_school_id,))

        class_assignments = fetch_all("""
            SELECT
                sc.*,
                t.full_name,
                s.school_name
            FROM school_classes sc
            LEFT JOIN teachers t ON sc.class_teacher_id = t.id
            LEFT JOIN schools s ON sc.school_id = s.id
            WHERE sc.school_id = ?
            ORDER BY sc.class_name
        """, (selected_school_id,))

    return render_template(
        "assign_class_teacher.html",
        schools=schools,
        teachers=teachers,
        classes=classes,
        assignments=class_assignments,
        selected_school_id=str(selected_school_id) if selected_school_id else ""
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
@app.route("/edit_cashbook_entry/<int:entry_id>")
@login_required
@roles_required("school_admin", "super_admin")
def edit_cashbook_entry(entry_id):

    school_id = session.get("school_id")

    entry = fetch_one("""
        SELECT *
        FROM cashbook
        WHERE id = ?
          AND school_id = ?
    """, (entry_id, school_id))

    if not entry:
        flash("Cashbook entry not found.", "danger")
        return redirect(url_for("cashbook"))

    return render_template(
        "edit_cashbook_entry.html",
        entry=entry
    )
@app.route("/update_cashbook_entry/<int:entry_id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def update_cashbook_entry(entry_id):

    school_id = session.get("school_id")

    entry = fetch_one("""
        SELECT *
        FROM cashbook
        WHERE id = ?
          AND school_id = ?
    """, (entry_id, school_id))

    if not entry:
        flash("Cashbook entry not found.", "danger")
        return redirect(url_for("cashbook"))

    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()
    payment_method = request.form.get("payment_method", "").strip()
    reference_number = request.form.get("reference_number", "").strip()

    amount = float(request.form.get("amount") or 0)

    execute_commit("""
        UPDATE cashbook
        SET
            description = ?,
            category = ?,
            payment_method = ?,
            reference_number = ?,
            amount = ?
        WHERE id = ?
          AND school_id = ?
    """, (
        description,
        category,
        payment_method,
        reference_number,
        amount,
        entry_id,
        school_id
    ))

    log_audit(
        "Updated cashbook entry",
        "cashbook",
        entry_id,
        f"Updated cashbook entry: {description}"
    )

    flash("Cashbook entry updated successfully.", "success")

    return redirect(url_for("cashbook"))

@app.route("/classes")
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def classes():
    school_id = session.get("school_id")
    role = session.get("role")

    selected_school = request.args.get("school_id")

    if role == "super_admin":
        schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

        query = """
            SELECT sc.id, sc.school_id, sc.class_name, s.school_name,
                   COUNT(st.id) AS total_students
            FROM school_classes sc
            LEFT JOIN schools s ON sc.school_id = s.id
            LEFT JOIN students st
                ON st.school_id = sc.school_id
                AND LOWER(TRIM(st.class_name)) = LOWER(TRIM(sc.class_name))
        """

        params = []

        if selected_school:
            query += " WHERE sc.school_id = ?"
            params.append(selected_school)

        query += """
            GROUP BY sc.id, sc.school_id, sc.class_name, s.school_name
            ORDER BY s.school_name, sc.class_name
        """

        class_rows = fetch_all(query, tuple(params))

        return render_template(
            "classes.html",
            classes=class_rows,
            schools=schools,
            selected_school=selected_school
        )

    else:
        class_rows = fetch_all("""
            SELECT sc.id, sc.school_id, sc.class_name,
                   COUNT(st.id) AS total_students
            FROM school_classes sc
            LEFT JOIN students st
                ON st.school_id = sc.school_id
                AND LOWER(TRIM(st.class_name)) = LOWER(TRIM(sc.class_name))
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

@app.route("/add_assessment", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin", "teacher")
def add_assessment():
    school_id = session.get("school_id")

    students = fetch_all(
        "SELECT id, first_name, last_name, class_name FROM students WHERE school_id = ?",
        (school_id,)
    )

    if request.method == "POST":
        student_id = request.form.get("student_id")
        subject = request.form.get("subject")
        term = request.form.get("term")
        assessment_type = request.form.get("assessment_type")
        marks = float(request.form.get("marks", 0))
        total_marks = float(request.form.get("total_marks", 0))
        comment = request.form.get("comment")

        percentage = 0
        if total_marks > 0:
            percentage = round((marks / total_marks) * 100, 2)

        student = fetch_one("SELECT class_name FROM students WHERE id = ?", (student_id,))

        execute_commit("""
            INSERT INTO assessments (
                student_id, school_id, class_name, subject, term,
                assessment_type, marks, total_marks, percentage, comment, date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_id,
            school_id,
            student["class_name"],
            subject,
            term,
            assessment_type,
            marks,
            total_marks,
            percentage,
            comment,
            datetime.now().strftime("%Y-%m-%d")
        ))

        flash("Assessment added successfully.", "success")
        return redirect(url_for("add_assessment"))

    return render_template("add_assessment.html", students=students)

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
@app.route("/year_end_promotion", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def year_end_promotion():
    school_id = session.get("school_id")
    role = session.get("role")

    schools = []
    selected_school_id = school_id

    if role == "super_admin":
        schools = fetch_all("SELECT * FROM schools ORDER BY school_name")
        selected_school_id = request.args.get("school_id") or request.form.get("school_id")

    academic_year = request.args.get("academic_year") or request.form.get("academic_year") or str(datetime.now().year)

    students = []
    already_done = False

    if selected_school_id:
        existing_batch = fetch_one("""
            SELECT *
            FROM promotion_batches
            WHERE school_id = ? AND academic_year = ?
        """, (selected_school_id, academic_year))

        already_done = existing_batch is not None

        student_rows = fetch_all("""
            SELECT 
                s.id,
                s.student_number,
                s.first_name,
                s.last_name,
                s.class_name,
                s.current_status,
                COALESCE(SUM(f.balance), 0) AS outstanding_balance
            FROM students s
            LEFT JOIN fees f ON s.id = f.student_id
            WHERE s.school_id = ?
              AND COALESCE(s.current_status, 'Active') = 'Active'
            GROUP BY s.id, s.student_number, s.first_name, s.last_name, s.class_name, s.current_status
            ORDER BY s.class_name, s.first_name, s.last_name
        """, (selected_school_id,))

        for student in student_rows:
            next_class = get_next_class(student["class_name"])

            students.append({
                "id": student["id"],
                "student_number": student["student_number"],
                "first_name": student["first_name"],
                "last_name": student["last_name"],
                "current_class": student["class_name"],
                "next_class": next_class,
                "outstanding_balance": float(student["outstanding_balance"] or 0),
                "will_graduate": next_class == "Graduated"
            })

    return render_template(
        "year_end_promotion.html",
        schools=schools,
        selected_school_id=selected_school_id,
        academic_year=academic_year,
        students=students,
        already_done=already_done
    )

@app.route("/run_year_end_promotion", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def run_year_end_promotion():
    role = session.get("role")
    school_id = session.get("school_id")

    if role == "super_admin":
        school_id = request.form.get("school_id")

    academic_year = request.form.get("academic_year") or str(datetime.now().year)

    if not school_id:
        flash("School is required.", "danger")
        return redirect(url_for("year_end_promotion"))

    existing_batch = fetch_one("""
        SELECT *
        FROM promotion_batches
        WHERE school_id = ? AND academic_year = ?
    """, (school_id, academic_year))

    if existing_batch:
        flash("Year-end promotion has already been run for this school and year.", "danger")
        return redirect(url_for("year_end_promotion", school_id=school_id, academic_year=academic_year))

    students = fetch_all("""
        SELECT *
        FROM students
        WHERE school_id = ?
          AND COALESCE(current_status, 'Active') = 'Active'
        ORDER BY class_name, first_name, last_name
    """, (school_id,))

    conn = get_db()
    cursor = conn.cursor()

    try:
        for student in students:
            student_id = student["id"]
            old_class = student["class_name"]
            new_class = get_next_class(old_class)

            balance_row = fetch_one("""
                SELECT COALESCE(SUM(balance), 0) AS total_balance
                FROM fees
                WHERE student_id = ?
                  AND school_id = ?
            """, (student_id, school_id))

            outstanding_balance = float(balance_row["total_balance"] or 0)

            if new_class == "Graduated":
                cursor.execute(
                    convert_query("""
                        UPDATE students
                        SET current_status = ?
                        WHERE id = ? AND school_id = ?
                    """),
                    ("Graduated", student_id, school_id)
                )
            else:
                cursor.execute(
                    convert_query("""
                        UPDATE students
                        SET class_name = ?
                        WHERE id = ? AND school_id = ?
                    """),
                    (new_class, student_id, school_id)
                )

                try:
                    cursor.execute(
                        convert_query("""
                            INSERT INTO school_classes (school_id, class_name)
                            VALUES (?, ?)
                        """),
                        (school_id, new_class)
                    )
                except Exception:
                    pass

            if outstanding_balance > 0:
                cursor.execute(
                    convert_query("""
                        INSERT INTO fees (
                            school_id, student_id, term_name, amount,
                            paid_amount, balance, status, due_date
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """),
                    (
                        school_id,
                        student_id,
                        f"Previous Year Balance {academic_year}",
                        outstanding_balance,
                        0,
                        outstanding_balance,
                        "Pending",
                        ""
                    )
                )

        cursor.execute(
            convert_query("""
                INSERT INTO promotion_batches (school_id, academic_year, promoted_by)
                VALUES (?, ?, ?)
            """),
            (school_id, academic_year, session.get("full_name", "System"))
        )

        conn.commit()

        log_audit(
            "Ran year-end promotion",
            "students",
            None,
            f"Promoted students for academic year {academic_year}"
        )

        flash("Year-end promotion completed successfully.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Year-end promotion failed: {str(e)}", "danger")

    finally:
        conn.close()

    return redirect(url_for("year_end_promotion", school_id=school_id, academic_year=academic_year))

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
@app.route("/import_teachers", methods=["GET", "POST"])
@login_required
@roles_required("super_admin")
def import_teachers():
    schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    if request.method == "POST":
        school_id = request.form.get("school_id")
        file = request.files.get("teacher_file")

        if not school_id or not file or not file.filename:
            flash("School and Excel file are required.", "danger")
            return redirect(url_for("import_teachers"))

        try:
            df = pd.read_excel(file)

            required_columns = ["full_name", "phone", "email", "username", "password"]
            missing = [c for c in required_columns if c not in df.columns]

            if missing:
                flash(f"Missing columns: {', '.join(missing)}", "danger")
                return redirect(url_for("import_teachers"))

            imported = 0
            skipped = 0

            for _, row in df.iterrows():
                full_name = str(row.get("full_name", "")).strip()
                phone = str(row.get("phone", "")).strip()
                email = str(row.get("email", "")).strip()
                username = str(row.get("username", "")).strip()
                password = str(row.get("password", "")).strip()

                if not full_name or not username or not password:
                    skipped += 1
                    continue

                existing = fetch_one("SELECT id FROM users WHERE username = ?", (username,))
                if existing:
                    skipped += 1
                    continue

                conn = get_db()
                cursor = conn.cursor()

                try:
                    if is_postgres():
                        cursor.execute(convert_query("""
                            INSERT INTO users (school_id, full_name, username, password, role)
                            VALUES (?, ?, ?, ?, ?)
                            RETURNING id
                        """), (
                            school_id,
                            full_name,
                            username,
                            generate_password_hash(password),
                            "teacher"
                        ))
                        user_id = cursor.fetchone()["id"]
                    else:
                        cursor.execute("""
                            INSERT INTO users (school_id, full_name, username, password, role)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            school_id,
                            full_name,
                            username,
                            generate_password_hash(password),
                            "teacher"
                        ))
                        user_id = cursor.lastrowid

                    cursor.execute(convert_query("""
                        INSERT INTO teachers (
                            school_id, user_id, teacher_id, full_name, phone, email
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """), (
                        school_id,
                        user_id,
                        generate_teacher_id(),
                        full_name,
                        phone,
                        email
                    ))

                    conn.commit()
                    imported += 1

                except Exception:
                    conn.rollback()
                    skipped += 1

                finally:
                    conn.close()

            log_audit(
                "Bulk imported teachers",
                "teachers",
                None,
                f"Imported {imported} teachers, skipped {skipped}"
            )

            flash(f"Teacher import complete. Imported: {imported}, Skipped: {skipped}", "success")
            return redirect(url_for("teachers"))

        except Exception as e:
            flash(f"Import failed: {str(e)}", "danger")
            return redirect(url_for("import_teachers"))

    return render_template("import_teachers.html", schools=schools)

@app.route("/import_fees", methods=["GET", "POST"])
@login_required
@roles_required("super_admin")
def import_fees():
    schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    if request.method == "POST":
        school_id = request.form.get("school_id")
        file = request.files.get("fee_file")

        if not school_id or not file or not file.filename:
            flash("School and Excel file are required.", "danger")
            return redirect(url_for("import_fees"))

        try:
            df = pd.read_excel(file)

            required_columns = [
                "student_number",
                "term_name",
                "amount",
                "paid_amount",
                "due_date"
            ]

            missing = [c for c in required_columns if c not in df.columns]

            if missing:
                flash(f"Missing columns: {', '.join(missing)}", "danger")
                return redirect(url_for("import_fees"))

            imported = 0
            skipped = 0

            for _, row in df.iterrows():
                student_number = str(row.get("student_number", "")).strip()
                term_name = str(row.get("term_name", "")).strip()
                due_date = str(row.get("due_date", "")).strip()

                try:
                    amount = float(row.get("amount", 0) or 0)
                    paid_amount = float(row.get("paid_amount", 0) or 0)
                except Exception:
                    skipped += 1
                    continue

                if not student_number or not term_name or amount <= 0:
                    skipped += 1
                    continue

                student = fetch_one("""
                    SELECT *
                    FROM students
                    WHERE student_number = ?
                      AND school_id = ?
                """, (student_number, school_id))

                if not student:
                    skipped += 1
                    continue

                existing_fee = fetch_one("""
                    SELECT id
                    FROM fees
                    WHERE school_id = ?
                      AND student_id = ?
                      AND term_name = ?
                """, (school_id, student["id"], term_name))

                if existing_fee:
                    skipped += 1
                    continue

                balance = amount - paid_amount

                if balance <= 0:
                    balance = 0
                    status = "Paid"
                elif paid_amount > 0:
                    status = "Partially Paid"
                else:
                    status = "Pending"

                execute_commit("""
                    INSERT INTO fees (
                        school_id,
                        student_id,
                        term_name,
                        amount,
                        paid_amount,
                        balance,
                        status,
                        due_date
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    school_id,
                    student["id"],
                    term_name,
                    amount,
                    paid_amount,
                    balance,
                    status,
                    due_date
                ))

                imported += 1

            log_audit(
                "Bulk imported fees",
                "fees",
                None,
                f"Imported {imported} fee records, skipped {skipped}"
            )

            flash(f"Fee import complete. Imported: {imported}, Skipped: {skipped}", "success")
            return redirect(url_for("fees"))

        except Exception as e:
            flash(f"Import failed: {str(e)}", "danger")
            return redirect(url_for("import_fees"))

    return render_template("import_fees.html", schools=schools)
@app.route("/import_fee_transactions", methods=["GET", "POST"])
@login_required
@roles_required("super_admin")
def import_fee_transactions():
    schools = fetch_all("SELECT * FROM schools ORDER BY school_name")

    if request.method == "POST":
        school_id = request.form.get("school_id")
        file = request.files.get("transaction_file")

        if not school_id or not file or not file.filename:
            flash("School and Excel file are required.", "danger")
            return redirect(url_for("import_fee_transactions"))

        try:
            df = pd.read_excel(file)

            required_columns = [
                "student_number",
                "payment_date",
                "details",
                "receipt_number",
                "amount",
                "term_name"
            ]

            missing = [c for c in required_columns if c not in df.columns]
            if missing:
                flash(f"Missing columns: {', '.join(missing)}", "danger")
                return redirect(url_for("import_fee_transactions"))

            imported = 0
            skipped = 0

            conn = get_db()
            cursor = conn.cursor()

            try:
                for _, row in df.iterrows():
                    student_number = str(row.get("student_number", "")).strip()
                    payment_date = str(row.get("payment_date", "")).strip()
                    details = str(row.get("details", "")).strip()
                    receipt_number = str(row.get("receipt_number", "")).strip()
                    term_name = str(row.get("term_name", "Term 1")).strip() or "Term 1"

                    try:
                        amount_paid = float(row.get("amount", 0) or 0)
                    except Exception:
                        skipped += 1
                        continue

                    if not student_number or amount_paid <= 0:
                        skipped += 1
                        continue

                    cursor.execute(convert_query("""
                        SELECT *
                        FROM students
                        WHERE student_number = ?
                          AND school_id = ?
                    """), (student_number, school_id))
                    student = cursor.fetchone()

                    if not student:
                        skipped += 1
                        continue

                    if receipt_number:
                        cursor.execute(convert_query("""
                            SELECT fp.id
                            FROM fee_payments fp
                            JOIN fees f ON fp.fee_id = f.id
                            WHERE f.school_id = ?
                              AND f.student_id = ?
                              AND fp.receipt_number = ?
                        """), (school_id, student["id"], receipt_number))
                        duplicate = cursor.fetchone()

                        if duplicate:
                            skipped += 1
                            continue

                    cursor.execute(convert_query("""
                        SELECT *
                        FROM fees
                        WHERE school_id = ?
                          AND student_id = ?
                          AND term_name = ?
                    """), (school_id, student["id"], term_name))
                    fee = cursor.fetchone()

                    if fee:
                        fee_id = fee["id"]
                        old_paid = float(fee["paid_amount"] or 0)
                        old_amount = float(fee["amount"] or 0)
                    else:
                        if is_postgres():
                            cursor.execute(convert_query("""
                                INSERT INTO fees (
                                    school_id,
                                    student_id,
                                    term_name,
                                    amount,
                                    paid_amount,
                                    balance,
                                    status,
                                    due_date
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                RETURNING id
                            """), (
                                school_id,
                                student["id"],
                                term_name,
                                0,
                                0,
                                0,
                                "Pending",
                                ""
                            ))
                            fee_id = cursor.fetchone()["id"]
                        else:
                            cursor.execute(convert_query("""
                                INSERT INTO fees (
                                    school_id,
                                    student_id,
                                    term_name,
                                    amount,
                                    paid_amount,
                                    balance,
                                    status,
                                    due_date
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """), (
                                school_id,
                                student["id"],
                                term_name,
                                0,
                                0,
                                0,
                                "Pending",
                                ""
                            ))
                            fee_id = cursor.lastrowid

                        old_paid = 0
                        old_amount = 0

                    cursor.execute(convert_query("""
                        INSERT INTO fee_payments (
                            school_id,
                            fee_id,
                            payment_date,
                            amount_paid,
                            receipt_number
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """), (
                        school_id,
                        fee_id,
                        payment_date,
                        amount_paid,
                        receipt_number
                    ))

                    new_paid = old_paid + amount_paid
                    new_amount = max(old_amount, new_paid)
                    new_balance = max(new_amount - new_paid, 0)

                    if new_balance <= 0:
                        status = "Paid"
                    elif new_paid > 0:
                        status = "Partially Paid"
                    else:
                        status = "Pending"

                    cursor.execute(convert_query("""
                        UPDATE fees
                        SET amount = ?,
                            paid_amount = ?,
                            balance = ?,
                            status = ?
                        WHERE id = ?
                    """), (
                        new_amount,
                        new_paid,
                        new_balance,
                        status,
                        fee_id
                    ))

                    student_name = f"{student['first_name']} {student['last_name']}".strip()

                    cursor.execute(convert_query("""
                        INSERT INTO cashbook (
                            school_id,
                            entry_date,
                            entry_type,
                            category,
                            description,
                            amount,
                            payment_method,
                            reference_number,
                            created_by
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """), (
                        school_id,
                        payment_date,
                        "income",
                        "School Fees",
                        f"{details} payment from {student_name}",
                        amount_paid,
                        "Imported Payment",
                        receipt_number,
                        session.get("full_name", "System")
                    ))

                    imported += 1

                conn.commit()

            except Exception:
                conn.rollback()
                raise

            finally:
                conn.close()

            log_audit(
                "Imported fee transactions",
                "fee_payments",
                None,
                f"Imported {imported} payment transactions, skipped {skipped}"
            )

            flash(
                f"Transaction import complete. Imported: {imported}, Skipped: {skipped}",
                "success"
            )
            return redirect(url_for("fees"))

        except Exception as e:
            flash(f"Import failed: {str(e)}", "danger")
            return redirect(url_for("import_fee_transactions"))

    return render_template("import_fee_transactions.html", schools=schools)

@app.route("/edit_fee/<int:fee_id>", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def edit_fee(fee_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        fee = fetch_one("""
            SELECT f.*, s.first_name, s.last_name, s.student_number, s.class_name
            FROM fees f
            JOIN students s ON f.student_id = s.id
            WHERE f.id = ?
        """, (fee_id,))
    else:
        fee = fetch_one("""
            SELECT f.*, s.first_name, s.last_name, s.student_number, s.class_name
            FROM fees f
            JOIN students s ON f.student_id = s.id
            WHERE f.id = ?
              AND f.school_id = ?
        """, (fee_id, school_id))

    if not fee:
        flash("Fee record not found or access denied.", "danger")
        return redirect(url_for("fees"))

    if request.method == "POST":
        term_name = request.form.get("term_name", "").strip()
        due_date = request.form.get("due_date", "").strip()

        try:
            amount = float(request.form.get("amount") or 0)
            paid_amount = float(request.form.get("paid_amount") or 0)
        except Exception:
            flash("Amount and paid amount must be valid numbers.", "danger")
            return redirect(url_for("edit_fee", fee_id=fee_id))

        if amount < 0 or paid_amount < 0:
            flash("Amounts cannot be negative.", "danger")
            return redirect(url_for("edit_fee", fee_id=fee_id))

        balance = amount - paid_amount

        if balance <= 0:
            balance = 0
            status = "Paid"
        elif paid_amount > 0:
            status = "Partially Paid"
        else:
            status = "Pending"

        execute_commit("""
            UPDATE fees
            SET term_name = ?,
                amount = ?,
                paid_amount = ?,
                balance = ?,
                status = ?,
                due_date = ?
            WHERE id = ?
        """, (
            term_name,
            amount,
            paid_amount,
            balance,
            status,
            due_date,
            fee_id
        ))

        log_audit(
            "Edited fee record",
            "fees",
            fee_id,
            f"Edited fee for {fee['first_name']} {fee['last_name']} - {term_name}"
        )

        flash("Fee record updated successfully.", "success")
        return redirect(url_for("fees"))

    return render_template("edit_fee.html", fee=fee)

@app.route("/set_class_fees", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def set_class_fees():
    school_id = session.get("school_id")
    role = session.get("role")

    schools = fetch_all("SELECT * FROM schools ORDER BY school_name") if role == "super_admin" else []

    selected_school_id = request.args.get("school_id") or school_id
    selected_class = request.args.get("class_name", "").strip()

    if request.method == "POST":
        if role == "super_admin":
            selected_school_id = request.form.get("school_id")

        class_name = request.form.get("class_name", "").strip()
        term_name = request.form.get("term_name", "").strip()
        due_date = request.form.get("due_date", "").strip()

        try:
            standard_amount = float(request.form.get("amount") or 0)
        except Exception:
            flash("Standard fee amount must be a number.", "danger")
            return redirect(url_for("set_class_fees"))

        if not selected_school_id or not class_name or not term_name or standard_amount <= 0:
            flash("School, class, term, and standard amount are required.", "danger")
            return redirect(url_for("set_class_fees"))

        students = fetch_all("""
            SELECT *
            FROM students
            WHERE school_id = ?
              AND class_name = ?
              AND COALESCE(current_status, 'Active') = 'Active'
            ORDER BY first_name, last_name
        """, (selected_school_id, class_name))

        created = 0
        updated = 0
        skipped = 0

        for student in students:
            custom_amount = request.form.get(f"amount_{student['id']}", "").strip()

            try:
                final_amount = float(custom_amount) if custom_amount else standard_amount
            except Exception:
                final_amount = standard_amount

            final_amount = max(final_amount, 0)

            existing = fetch_one("""
                SELECT id
                FROM fees
                WHERE school_id = ?
                  AND student_id = ?
                  AND term_name = ?
            """, (
                selected_school_id,
                student["id"],
                term_name
            ))

            if existing:
                fee_id = existing["id"]

                paid_row = fetch_one("""
                    SELECT COALESCE(SUM(amount_paid), 0) AS total_paid
                    FROM fee_payments
                    WHERE fee_id = ?
                """, (fee_id,))

                paid_amount = float(paid_row["total_paid"] or 0)

                balance = max(final_amount - paid_amount, 0)

                if balance <= 0:
                    status = "Paid"
                elif paid_amount > 0:
                    status = "Partially Paid"
                else:
                    status = "Pending"

                execute_commit("""
                    UPDATE fees
                    SET amount = ?,
                        paid_amount = ?,
                        balance = ?,
                        status = ?,
                        due_date = ?
                    WHERE id = ?
                """, (
                    final_amount,
                    paid_amount,
                    balance,
                    status,
                    due_date,
                    fee_id
                ))

                updated += 1
                continue

            execute_commit("""
                INSERT INTO fees (
                    school_id,
                    student_id,
                    term_name,
                    amount,
                    paid_amount,
                    balance,
                    status,
                    due_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                selected_school_id,
                student["id"],
                term_name,
                final_amount,
                0,
                final_amount,
                "Pending",
                due_date
            ))

            created += 1

        log_audit(
            "Set or reset class fees",
            "fees",
            None,
            f"{class_name} | {term_name} | Created={created} | Updated={updated} | Skipped={skipped}"
        )

        flash(
            f"Class fees processed successfully. Created: {created}, Updated: {updated}, Skipped: {skipped}",
            "success"
        )

        return redirect(url_for("fees"))

    class_rows = []
    students = []

    if selected_school_id:
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM students
            WHERE school_id = ?
              AND class_name IS NOT NULL
              AND class_name <> ''
            ORDER BY class_name
        """, (selected_school_id,))

    if selected_school_id and selected_class:
        students = fetch_all("""
            SELECT *
            FROM students
            WHERE school_id = ?
              AND class_name = ?
              AND COALESCE(current_status, 'Active') = 'Active'
            ORDER BY first_name, last_name
        """, (
            selected_school_id,
            selected_class
        ))

    return render_template(
        "set_class_fees.html",
        schools=schools,
        class_rows=class_rows,
        students=students,
        selected_school_id=str(selected_school_id) if selected_school_id else "",
        selected_class=selected_class
    )

@app.route("/reset_user_password/<int:user_id>", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def reset_user_password(user_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        user = fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
    else:
        user = fetch_one(
            "SELECT * FROM users WHERE id = ? AND school_id = ? AND role IN ('teacher', 'parent')",
            (user_id, school_id)
        )

    if not user:
        flash("User not found or access denied.", "danger")
        return redirect(url_for("users"))

    if user["role"] == "super_admin" and role != "super_admin":
        flash("Only super admin can reset a super admin password.", "danger")
        return redirect(url_for("users"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not new_password or new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("reset_user_password", user_id=user_id))

        if len(new_password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("reset_user_password", user_id=user_id))

        execute_commit(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(new_password), user_id)
        )

        log_audit(
            "Reset user password",
            "users",
            user_id,
            f"Password reset for {user['username']}"
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
    log_audit(
    "Deactivated user",
    "users",
    user_id,
    f"Deactivated {user['username']}"
)
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
    log_audit(
    "Activated user",
    "users",
    user_id,
    f"Activated {user['username']}"
)
    return redirect(url_for("users"))

@app.route("/edit_school/<int:school_id>", methods=["GET", "POST"])
@login_required
@roles_required("super_admin")
def edit_school(school_id):
    school = fetch_one("SELECT * FROM schools WHERE id = ?", (school_id,))

    if not school:
        flash("School not found.", "danger")
        return redirect(url_for("schools"))

    if request.method == "POST":
        school_name = request.form.get("school_name", "").strip()
        school_code = request.form.get("school_code", "").strip()

        if not school_name:
            flash("School name is required.", "danger")
            return redirect(url_for("edit_school", school_id=school_id))

        logo_url = row_get(school, "logo_url", "")

        logo_file = request.files.get("logo_file")
        if logo_file and logo_file.filename:
            if not allowed_logo_file(logo_file.filename):
                flash("Logo must be PNG, JPG, JPEG, or WEBP.", "danger")
                return redirect(url_for("edit_school", school_id=school_id))

            original_name = secure_filename(logo_file.filename)
            ext = original_name.rsplit(".", 1)[1].lower()
            saved_name = f"school_logo_{school_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"

            logo_path = os.path.join(LOGO_UPLOAD_FOLDER, saved_name)
            logo_file.save(logo_path)

            logo_url = f"uploads/logos/{saved_name}"

        execute_commit("""
            UPDATE schools
            SET school_name = ?, school_code = ?, logo_url = ?
            WHERE id = ?
        """, (school_name, school_code, logo_url, school_id))

        log_audit(
            "Updated school branding",
            "schools",
            school_id,
            f"Updated school name/logo for {school_name}"
        )

        flash("School branding updated successfully.", "success")
        return redirect(url_for("schools"))

    return render_template("edit_school.html", school=school)

      

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

ALLOWED_RESOURCE_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx",
    "xls", "xlsx", "txt", "png", "jpg", "jpeg"
}

def allowed_resource_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_RESOURCE_EXTENSIONS
    )

@app.route("/upload_resource", methods=["GET", "POST"])
@login_required
@roles_required("teacher", "school_admin", "super_admin")
def upload_resource():
    school_id = session.get("school_id")
    role = session.get("role")
    user_id = session.get("user_id")

    teacher = None
    class_options = []
    subjects = []

    if role == "teacher":
        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE user_id = ? AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if not teacher:
            flash("No teacher profile linked to this account.", "danger")
            return redirect(url_for("teacher_dashboard"))

        assignments = fetch_all("""
            SELECT DISTINCT class_name, subject
            FROM teacher_assignments
            WHERE teacher_id = ?
              AND school_id = ?
            ORDER BY class_name, subject
        """, (teacher["id"], school_id))

        class_options = sorted(list(set([a["class_name"] for a in assignments])))
        subjects = sorted(list(set([a["subject"] for a in assignments])))

    else:
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM school_classes
            WHERE school_id = ?
            ORDER BY class_name
        """, (school_id,))

        subject_rows = fetch_all("""
            SELECT subject_name
            FROM subjects
            WHERE school_id = ?
            ORDER BY subject_name
        """, (school_id,))

        class_options = [c["class_name"] for c in class_rows]
        subjects = [s["subject_name"] for s in subject_rows]

    if request.method == "POST":
        class_name = request.form.get("class_name", "").strip()
        subject = request.form.get("subject", "").strip()
        term = request.form.get("term", "").strip()
        title = request.form.get("title", "").strip()
        resource_type = request.form.get("resource_type", "").strip()
        file = request.files.get("resource_file")

        if not class_name or not subject or not term or not title or not resource_type or not file:
            flash("All fields and file upload are required.", "danger")
            return redirect(url_for("upload_resource"))

        if not allowed_resource_file(file.filename):
            flash("Invalid file type. Allowed: PDF, Word, PowerPoint, Excel, PNG, JPG.", "danger")
            return redirect(url_for("upload_resource"))

        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit(".", 1)[1].lower()
        saved_filename = f"resource_{school_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000,9999)}.{ext}"

        file_path = os.path.join(UPLOAD_FOLDER, saved_filename)
        file.save(file_path)

        teacher_id = teacher["id"] if teacher else None

        execute_commit("""
            INSERT INTO teacher_resources (
                school_id, teacher_id, class_name, subject, term,
                title, resource_type, filename, original_filename, uploaded_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            school_id,
            teacher_id,
            class_name,
            subject,
            term,
            title,
            resource_type,
            saved_filename,
            original_filename,
            session.get("full_name", "System")
        ))

        log_audit(
            "Uploaded teacher resource",
            "teacher_resources",
            None,
            f"{title} - {class_name} - {subject}"
        )

        flash("Resource uploaded successfully.", "success")
        return redirect(url_for("teacher_resources"))

    return render_template(
        "upload_resource.html",
        class_options=class_options,
        subjects=subjects
    )
@app.route("/teacher_resources")
@login_required
@roles_required("teacher", "school_admin", "super_admin", "parent")
def teacher_resources():
    school_id = session.get("school_id")
    role = session.get("role")
    user_id = session.get("user_id")

    class_filter = request.args.get("class_name", "").strip()
    subject_filter = request.args.get("subject", "").strip()
    term_filter = request.args.get("term", "").strip()

    query = """
        SELECT tr.*, t.full_name AS teacher_name
        FROM teacher_resources tr
        LEFT JOIN teachers t ON tr.teacher_id = t.id
        WHERE 1=1
    """
    params = []

    if role != "super_admin":
        query += " AND tr.school_id = ?"
        params.append(school_id)

    if role == "teacher":
        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE user_id = ? AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if teacher:
            query += " AND tr.teacher_id = ?"
            params.append(teacher["id"])

    if role == "parent":
        student = fetch_one("""
            SELECT s.*
            FROM students s
            JOIN guardians g ON s.id = g.student_id
            WHERE g.parent_user_id = ?
              AND s.school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if student:
            query += " AND tr.class_name = ?"
            params.append(student["class_name"])
        else:
            query += " AND 1=0"

    if class_filter:
        query += " AND tr.class_name = ?"
        params.append(class_filter)

    if subject_filter:
        query += " AND tr.subject = ?"
        params.append(subject_filter)

    if term_filter:
        query += " AND tr.term = ?"
        params.append(term_filter)

    query += " ORDER BY tr.uploaded_at DESC"

    resources = fetch_all(query, tuple(params))

    class_options = sorted(list(set([r["class_name"] for r in resources if r["class_name"]])))
    subjects = sorted(list(set([r["subject"] for r in resources if r["subject"]])))

    return render_template(
        "teacher_resources.html",
        resources=resources,
        class_options=class_options,
        subjects=subjects,
        class_filter=class_filter,
        subject_filter=subject_filter,
        term_filter=term_filter
    )
@app.route("/fix_fee_payment_details")
@login_required
@roles_required("super_admin")
def fix_fee_payment_details():
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            ALTER TABLE fee_payments
            ADD COLUMN IF NOT EXISTS details TEXT
        """)
        conn.commit()
        return "fee_payments.details column added successfully"
    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}"
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

def run_school_logo_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("ALTER TABLE schools ADD COLUMN IF NOT EXISTS logo_url TEXT")
        else:
            try:
                cursor.execute("ALTER TABLE schools ADD COLUMN logo_url TEXT")
            except Exception:
                pass

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
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():

            # ➤ Add new columns safely
            cursor.execute("ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS entry_type VARCHAR(50)")
            cursor.execute("ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS category VARCHAR(100)")
            cursor.execute("ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50)")
            cursor.execute("ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS reference_number TEXT")
            cursor.execute("ALTER TABLE cashbook ADD COLUMN IF NOT EXISTS created_by TEXT")

            # ➤ Try to migrate old data safely
            try:
                cursor.execute("""
                    UPDATE cashbook
                    SET entry_type = type
                    WHERE entry_type IS NULL AND type IS NOT NULL
                """)
            except Exception:
                conn.rollback()

            try:
                cursor.execute("""
                    UPDATE cashbook
                    SET created_by = recorded_by
                    WHERE created_by IS NULL AND recorded_by IS NOT NULL
                """)
            except Exception:
                conn.rollback()

            # ➤ Set safe defaults
            cursor.execute("""
                UPDATE cashbook
                SET category = 'General'
                WHERE category IS NULL OR category = ''
            """)

            cursor.execute("""
                UPDATE cashbook
                SET payment_method = ''
                WHERE payment_method IS NULL
            """)

            cursor.execute("""
                UPDATE cashbook
                SET reference_number = ''
                WHERE reference_number IS NULL
            """)

        else:
            # SQLITE VERSION

            def safe_add(column_sql):
                try:
                    cursor.execute(column_sql)
                except Exception:
                    pass

            safe_add("ALTER TABLE cashbook ADD COLUMN entry_type TEXT")
            safe_add("ALTER TABLE cashbook ADD COLUMN category TEXT")
            safe_add("ALTER TABLE cashbook ADD COLUMN payment_method TEXT")
            safe_add("ALTER TABLE cashbook ADD COLUMN reference_number TEXT")
            safe_add("ALTER TABLE cashbook ADD COLUMN created_by TEXT")

            # Try migrating old fields
            try:
                cursor.execute("""
                    UPDATE cashbook
                    SET entry_type = type
                    WHERE entry_type IS NULL AND type IS NOT NULL
                """)
            except Exception:
                pass

            try:
                cursor.execute("""
                    UPDATE cashbook
                    SET created_by = recorded_by
                    WHERE created_by IS NULL AND recorded_by IS NOT NULL
                """)
            except Exception:
                pass

            cursor.execute("""
                UPDATE cashbook
                SET category = 'General'
                WHERE category IS NULL OR category = ''
            """)

        conn.commit()
        print("Cashbook migration completed")

    except Exception as e:
        conn.rollback()
        print("CASHBOOK MIGRATION ERROR:", str(e))

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
def run_fee_payments_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                ALTER TABLE fee_payments
                ADD COLUMN IF NOT EXISTS details TEXT
            """)
        else:
            try:
                cursor.execute("""
                    ALTER TABLE fee_payments
                    ADD COLUMN details TEXT
                """)
            except Exception:
                pass

        conn.commit()
    finally:
        conn.close()

def create_year_end_tables():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS promotion_batches (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER,
                    academic_year VARCHAR(20),
                    promoted_by VARCHAR(255),
                    promoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(school_id, academic_year)
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS promotion_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER,
                    academic_year TEXT,
                    promoted_by TEXT,
                    promoted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(school_id, academic_year)
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

            run_waiting_list_migration()
            print("Waiting list migration completed")

            run_waiting_list_migration()
            print("Waiting list migration completed")
            
            run_audit_migration()
            print("Audit migration completed")

            add_school_id_to_audit_logs()
            print("Audit school_id migration completed")

            run_school_logo_migration()
            print("School logo migration completed")

            run_fee_payments_migration()
            print("Fee payments migration completed")

            create_year_end_tables()
            print("Year-end promotion tables ready")
            
            create_default_school()
            print("Default school ready")

            assign_existing_data_to_default_school()
            print("Old data linked to default school")

            migrate_roles()
            print("Roles migrated")

            create_super_admin()
            print("Super admin ready")

            create_teacher_resources_table()
            print("Teacher resources table ready")

            update_school_subscription_states()
            print("School subscription states updated")

        print("Setup complete")
    except Exception as e:
        print("SETUP ERROR:", e)



def create_teacher_resources_table():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teacher_resources (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER,
                    teacher_id INTEGER,
                    class_name VARCHAR(100),
                    subject VARCHAR(100),
                    term VARCHAR(50),
                    title VARCHAR(255),
                    resource_type VARCHAR(100),
                    filename TEXT,
                    original_filename TEXT,
                    uploaded_by VARCHAR(255),
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS teacher_resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER,
                    teacher_id INTEGER,
                    class_name TEXT,
                    subject TEXT,
                    term TEXT,
                    title TEXT,
                    resource_type TEXT,
                    filename TEXT,
                    original_filename TEXT,
                    uploaded_by TEXT,
                    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
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

@app.route("/import_students", methods=["GET", "POST"])
@login_required
@roles_required("super_admin")
def import_students():
    school_id = session.get("school_id")
    role = session.get("role")

    schools = fetch_all("SELECT * FROM schools ORDER BY school_name") if role == "super_admin" else []

    if request.method == "POST":
        if role == "super_admin":
            school_id = request.form.get("school_id")

        file = request.files.get("student_file")

        if not school_id:
            flash("School is required.", "danger")
            return redirect(url_for("import_students"))

        if not file or not file.filename:
            flash("Please upload an Excel file.", "danger")
            return redirect(url_for("import_students"))

        try:
            df = pd.read_excel(file)

            required_columns = [
                "first_name",
                "last_name",
                "gender",
                "birthday",
                "class_name",
                "guardian1_name",
                "guardian1_phone",
                "guardian1_email"
            ]

            missing = [c for c in required_columns if c not in df.columns]

            if missing:
                flash(f"Missing columns: {', '.join(missing)}", "danger")
                return redirect(url_for("import_students"))

            imported = 0
            skipped = 0

            for _, row in df.iterrows():
                first_name = str(row.get("first_name", "")).strip()
                last_name = str(row.get("last_name", "")).strip()
                class_name = str(row.get("class_name", "")).strip()

                if not first_name or not last_name or not class_name:
                    skipped += 1
                    continue

                student_number = generate_student_number()
                existing = fetch_one("""
                    SELECT id
                    FROM students
                    WHERE school_id = ?
                    AND first_name = ?
                    AND last_name = ?
                    AND class_name = ?
                """, (
                    school_id,
                    first_name,
                    last_name,
                     class_name
                ))

                if existing:
                    skipped += 1
                    continue
                execute_commit("""
                    INSERT INTO students (
                        school_id,
                        student_number,
                        first_name,
                        last_name,
                        gender,
                        birthday,
                        class_name,
                        guardian1_name,
                        guardian1_phone,
                        guardian1_email,
                        current_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    school_id,
                    student_number,
                    first_name,
                    last_name,
                    str(row.get("gender", "")).strip(),
                    str(row.get("birthday", "")).strip(),
                    class_name,
                    str(row.get("guardian1_name", "")).strip(),
                    str(row.get("guardian1_phone", "")).strip(),
                    str(row.get("guardian1_email", "")).strip(),
                    "Active"
                ))

                imported += 1

            log_audit(
                "Bulk imported students",
                "students",
                None,
                f"Imported {imported} students, skipped {skipped}"
            )

            flash(f"Import complete. Imported: {imported}, Skipped: {skipped}", "success")
            return redirect(url_for("students"))

        except Exception as e:
            flash(f"Import failed: {str(e)}", "danger")
            return redirect(url_for("import_students"))

    return render_template("import_students.html", schools=schools)

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


@app.route("/debug_students")
@login_required
@roles_required("super_admin")
def debug_students():
    total = fetch_one("SELECT COUNT(*) AS total FROM students")

    students = fetch_all("""
        SELECT id, school_id, student_number, first_name, last_name, class_name, current_status
        FROM students
        ORDER BY id DESC
        LIMIT 300
    """)

    output = f"<h2>Total students in database: {total['total']}</h2>"

    if not students:
        output += "<p>No students found in students table.</p>"
        return output

    for s in students:
        output += f"""
        <p>
            <strong>ID:</strong> {s['id']} |
            <strong>School:</strong> {s['school_id']} |
            <strong>No:</strong> {s['student_number']} |
            <strong>Name:</strong> {s['first_name']} {s['last_name']} |
            <strong>Class:</strong> {s['class_name']} |
            <strong>Status:</strong> {s['current_status']}
        </p>
        """

    return output

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

@app.route("/fix_timetable_class_names")
@login_required
@roles_required("super_admin")
def fix_timetable_class_names():
    updates = [
        ("1 Blue", "Form 1 Blue"),
        ("1 Grey", "Form 1 Grey"),
        ("2 Blue", "Form 2 Blue"),
        ("2 Grey", "Form 2 Grey"),
        ("3 Blue", "Form 3 Blue"),
        ("3 Grey", "Form 3 Grey"),
        ("4 Blue", "Form 4 Blue"),
        ("4 Grey", "Form 4 Grey"),
        ("Form5", "Form 5"),
        ("Form6", "Form 6"),
    ]

    for old, new in updates:
        execute_commit(
            "UPDATE timetables SET class_name = ? WHERE class_name = ?",
            (new, old)
        )

    return "Timetable class names fixed successfully."

@app.route("/debug_timetable")
@login_required
@roles_required("super_admin", "school_admin")
def debug_timetable():
    rows = fetch_all("""
        SELECT *
        FROM timetables
        ORDER BY id DESC
        LIMIT 100
    """)

    return "<pre>" + str(rows) + "</pre>"

if __name__ == "__main__":
    setup_app()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)