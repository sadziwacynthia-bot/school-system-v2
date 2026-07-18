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
from routes.teachers import register_teacher_routes
from routes.admin import register_admin_routes
from utils.storage import upload_to_supabase
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
register_teacher_routes(app)
register_admin_routes(app)

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
    user_id = session.get("user_id")

    class_filter = request.args.get("class_name", "").strip()
    term_filter = request.args.get("term", "").strip()
    search = request.args.get("search", "").strip()

    conditions = []
    params = []

    query = """
        SELECT
            r.student_id,
            r.class_name,
            r.term,
            s.student_number,
            s.first_name,
            s.last_name,
            COUNT(r.id) AS subject_count,
            COALESCE(SUM(r.marks), 0) AS total_marks,
            COALESCE(AVG(r.marks), 0) AS average_marks
        FROM results r
        JOIN students s ON r.student_id = s.id
    """

    if role != "super_admin":
        conditions.append("r.school_id = ?")
        params.append(school_id)

    if role == "teacher":
        teacher = fetch_one("""
            SELECT id
            FROM teachers
            WHERE user_id = ?
              AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if not teacher:
            conditions.append("1 = 0")
        else:
            conditions.append("""
                EXISTS (
                    SELECT 1
                    FROM teacher_assignments ta
                    WHERE ta.teacher_id = ?
                      AND ta.school_id = r.school_id
                      AND ta.class_name = r.class_name
                      AND ta.subject = r.subject
                )
            """)
            params.append(teacher["id"])

    if class_filter:
        conditions.append("r.class_name = ?")
        params.append(class_filter)

    if term_filter:
        conditions.append("r.term = ?")
        params.append(term_filter)

    if search:
        conditions.append("""
            (
                s.first_name LIKE ?
                OR s.last_name LIKE ?
                OR s.student_number LIKE ?
            )
        """)
        like = f"%{search}%"
        params.extend([like, like, like])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += """
        GROUP BY
            r.student_id,
            r.class_name,
            r.term,
            s.student_number,
            s.first_name,
            s.last_name
        ORDER BY
            r.class_name,
            s.last_name,
            s.first_name,
            r.term
    """

    result_groups = fetch_all(query, tuple(params))

    class_conditions = []
    class_params = []

    if role != "super_admin":
        class_conditions.append("school_id = ?")
        class_params.append(school_id)

    class_query = """
        SELECT DISTINCT class_name
        FROM results
    """

    if class_conditions:
        class_query += " WHERE " + " AND ".join(class_conditions)
        class_query += """
            AND class_name IS NOT NULL
            AND TRIM(class_name) != ''
        """
    else:
        class_query += """
            WHERE class_name IS NOT NULL
              AND TRIM(class_name) != ''
        """

    class_query += " ORDER BY class_name"

    classes = fetch_all(class_query, tuple(class_params))

    return render_template(
        "results.html",
        result_groups=result_groups,
        classes=classes,
        class_filter=class_filter,
        term_filter=term_filter,
        search=search
    )

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

    selected_class = (
        request.form.get("class_name", "").strip()
        if request.method == "POST"
        else request.args.get("class_name", "").strip()
    )

    attendance_date = (
        request.form.get("attendance_date", "").strip()
        if request.method == "POST"
        else datetime.now().strftime("%Y-%m-%d")
    )

    students_list = []
    class_options = []
    teacher = None

    # =====================================================
    # TEACHER VIEW
    # =====================================================
    if role == "teacher":
        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE user_id = ?
              AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if not teacher:
            flash("No teacher profile is linked to this account.", "danger")

            return render_template(
                "attendance.html",
                class_options=[],
                selected_class="",
                students=[],
                today=attendance_date
            )

        class_teacher_rows = fetch_all("""
            SELECT class_name
            FROM school_classes
            WHERE class_teacher_id = ?
              AND school_id = ?
            ORDER BY class_name
        """, (teacher["id"], school_id))

        class_options = [
            row["class_name"]
            for row in class_teacher_rows
            if row["class_name"]
        ]

        if not selected_class and len(class_options) == 1:
            selected_class = class_options[0]

        if selected_class and selected_class not in class_options:
            flash(
                "You can only take attendance for your assigned class.",
                "danger"
            )
            selected_class = ""

    # =====================================================
    # SUPER ADMIN VIEW
    # =====================================================
    elif role == "super_admin":
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM school_classes
            WHERE class_name IS NOT NULL
              AND TRIM(class_name) != ''
            ORDER BY class_name
        """)

        class_options = [
            row["class_name"]
            for row in class_rows
        ] or CLASS_OPTIONS

    # =====================================================
    # SCHOOL ADMIN VIEW
    # =====================================================
    else:
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM school_classes
            WHERE school_id = ?
              AND class_name IS NOT NULL
              AND TRIM(class_name) != ''
            ORDER BY class_name
        """, (school_id,))

        class_options = [
            row["class_name"]
            for row in class_rows
        ] or CLASS_OPTIONS

    # =====================================================
    # LOAD ACTIVE STUDENTS
    # =====================================================
    if selected_class:
        if role == "super_admin":
            students_list = fetch_all("""
                SELECT *
                FROM students
                WHERE class_name = ?
                  AND COALESCE(current_status, 'Active') = 'Active'
                ORDER BY first_name, last_name
            """, (selected_class,))
        else:
            students_list = fetch_all("""
                SELECT *
                FROM students
                WHERE school_id = ?
                  AND class_name = ?
                  AND COALESCE(current_status, 'Active') = 'Active'
                ORDER BY first_name, last_name
            """, (school_id, selected_class))

    # =====================================================
    # SAVE ATTENDANCE
    # =====================================================
    if request.method == "POST":
        if not selected_class:
            flash("Please select a class.", "danger")
            return redirect(url_for("attendance"))

        if not attendance_date:
            flash("Attendance date is required.", "danger")
            return redirect(
                url_for("attendance", class_name=selected_class)
            )

        if not students_list:
            flash(
                "No active students were found in the selected class.",
                "warning"
            )
            return redirect(
                url_for("attendance", class_name=selected_class)
            )

        allowed_statuses = {
            "Present",
            "Absent",
            "Late",
            "Excused"
        }

        conn = get_db()
        cursor = conn.cursor()

        try:
            for student in students_list:
                student_id = student["id"]

                status = request.form.get(
                    f"status_{student_id}",
                    "Present"
                ).strip()

                if status not in allowed_statuses:
                    status = "Present"

                # Prevent duplicate attendance for the same student/date.
                if role == "super_admin":
                    cursor.execute(
                        convert_query("""
                            DELETE FROM attendance
                            WHERE student_id = ?
                              AND class_name = ?
                              AND date = ?
                        """),
                        (
                            student_id,
                            selected_class,
                            attendance_date
                        )
                    )
                else:
                    cursor.execute(
                        convert_query("""
                            DELETE FROM attendance
                            WHERE school_id = ?
                              AND student_id = ?
                              AND class_name = ?
                              AND date = ?
                        """),
                        (
                            school_id,
                            student_id,
                            selected_class,
                            attendance_date
                        )
                    )

                record_school_id = (
                    student["school_id"]
                    if role == "super_admin"
                    else school_id
                )

                cursor.execute(
                    convert_query("""
                        INSERT INTO attendance (
                            school_id,
                            student_id,
                            class_name,
                            date,
                            status
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """),
                    (
                        record_school_id,
                        student_id,
                        selected_class,
                        attendance_date,
                        status
                    )
                )

            conn.commit()

            log_audit(
                "Recorded attendance",
                "attendance",
                None,
                f"{selected_class} attendance for {attendance_date}"
            )

            flash(
                f"Attendance for {selected_class} was saved successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "attendance",
                    class_name=selected_class,
                    date=attendance_date
                )
            )

        except Exception as error:
            conn.rollback()
            app.logger.exception("Attendance saving failed")

            flash(
                f"Attendance could not be saved: {str(error)}",
                "danger"
            )

        finally:
            conn.close()

    # =====================================================
    # LOAD EXISTING ATTENDANCE
    # =====================================================
    existing_attendance = {}

    if selected_class and students_list:
        attendance_params = [selected_class, attendance_date]

        attendance_query = """
            SELECT student_id, status
            FROM attendance
            WHERE class_name = ?
              AND date = ?
        """

        if role != "super_admin":
            attendance_query += " AND school_id = ?"
            attendance_params.append(school_id)

        attendance_rows = fetch_all(
            attendance_query,
            tuple(attendance_params)
        )

        existing_attendance = {
            row["student_id"]: row["status"]
            for row in attendance_rows
        }

    return render_template(
        "attendance.html",
        class_options=class_options,
        selected_class=selected_class,
        students=students_list,
        today=attendance_date,
        existing_attendance=existing_attendance
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
@app.route("/reports/cashbook")
@login_required
@roles_required("school_admin", "super_admin")
def cashbook_report():
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

    category_query = """
        SELECT DISTINCT category
        FROM cashbook
        WHERE category IS NOT NULL
          AND TRIM(category) != ''
    """
    category_params = []

    if role != "super_admin":
        category_query += " AND school_id = ?"
        category_params.append(school_id)

    category_query += " ORDER BY category"

    categories = fetch_all(
        category_query,
        tuple(category_params)
    )

    return render_template(
        "reports/cashbook_report.html",
        entries=processed_entries,
        categories=categories,
        entry_type=entry_type,
        category=category,
        source=source,
        start_date=start_date,
        end_date=end_date,
        total_income=total_income,
        total_expense=total_expense,
        net_balance=net_balance
    )
@app.route("/reports/student-list")
@login_required
@roles_required("school_admin", "super_admin")
def student_list_report():

    school_id = session.get("school_id")
    role = session.get("role")

    search = request.args.get("search","").strip()
    class_name = request.args.get("class_name","").strip()
    status = request.args.get("status","").strip()

    query = """
        SELECT *,
        COALESCE(current_status,'Active') AS status
        FROM students
        WHERE 1=1
    """

    params=[]

    if role!="super_admin":
        query+=" AND school_id=?"
        params.append(school_id)

    if search:
        query+="""
        AND(
            first_name LIKE ?
            OR last_name LIKE ?
            OR student_number LIKE ?
        )
        """
        like=f"%{search}%"
        params.extend([like,like,like])

    if class_name:
        query+=" AND class_name=?"
        params.append(class_name)

    if status:
        query+=" AND COALESCE(current_status,'Active')=?"
        params.append(status)

    query+=" ORDER BY class_name,last_name,first_name"

    students=fetch_all(query,tuple(params))

    class_query="""
    SELECT DISTINCT class_name
    FROM students
    WHERE class_name IS NOT NULL
    """

    class_params=[]

    if role!="super_admin":
        class_query+=" AND school_id=?"
        class_params.append(school_id)

    class_query+=" ORDER BY class_name"

    classes=fetch_all(class_query,tuple(class_params))

    total_students=len(students)
    active=sum(1 for s in students if (s["status"] or "Active")=="Active")
    inactive=total_students-active

    return render_template(
        "reports/student_list.html",
        students=students,
        classes=classes,
        search=search,
        selected_class=class_name,
        selected_status=status,
        total_students=total_students,
        active_students=active,
        inactive_students=inactive
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

    # =====================================================
    # LOAD TEACHER ASSIGNMENTS
    # =====================================================
    if role == "teacher":
        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE user_id = ?
              AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if not teacher:
            flash("No teacher profile is linked to this account.", "danger")
            return redirect(url_for("teacher_dashboard"))

        assignments = fetch_all("""
            SELECT DISTINCT class_name, subject
            FROM teacher_assignments
            WHERE teacher_id = ?
              AND school_id = ?
            ORDER BY class_name, subject
        """, (teacher["id"], school_id))

        class_options = sorted({
            row["class_name"]
            for row in assignments
            if row["class_name"]
        })

        subjects = sorted({
            row["subject"]
            for row in assignments
            if row["subject"]
        })

    # =====================================================
    # LOAD ADMIN OPTIONS
    # =====================================================
    else:
        class_rows = fetch_all("""
            SELECT DISTINCT class_name
            FROM school_classes
            WHERE school_id = ?
              AND class_name IS NOT NULL
              AND TRIM(class_name) != ''
            ORDER BY class_name
        """, (school_id,))

        subject_rows = fetch_all("""
            SELECT subject_name
            FROM subjects
            WHERE school_id = ?
              AND subject_name IS NOT NULL
              AND TRIM(subject_name) != ''
            ORDER BY subject_name
        """, (school_id,))

        class_options = [
            row["class_name"]
            for row in class_rows
        ]

        subjects = [
            row["subject_name"]
            for row in subject_rows
        ]

    # =====================================================
    # HANDLE UPLOAD
    # =====================================================
    if request.method == "POST":
        class_name = request.form.get("class_name", "").strip()
        subject = request.form.get("subject", "").strip()
        term = request.form.get("term", "").strip()
        title = request.form.get("title", "").strip()
        resource_type = request.form.get("resource_type", "").strip()
        file = request.files.get("resource_file")

        if (
            not class_name
            or not subject
            or not term
            or not title
            or not resource_type
            or not file
            or not file.filename
        ):
            flash("All fields and a file are required.", "danger")
            return redirect(url_for("upload_resource"))

        if role == "teacher":
            if class_name not in class_options or subject not in subjects:
                flash(
                    "You can only upload resources for your assigned classes and subjects.",
                    "danger"
                )
                return redirect(url_for("upload_resource"))

        if not allowed_resource_file(file.filename):
            flash(
                "Invalid file type. Allowed files: PDF, Word, PowerPoint, Excel, PNG and JPG.",
                "danger"
            )
            return redirect(url_for("upload_resource"))

        try:
            uploaded = upload_to_supabase(
                file,
                folder=f"resources/school_{school_id}"
            )

            if not uploaded:
                raise RuntimeError("Storage returned no upload result.")

            saved_filename = uploaded.get("url")
            original_filename = uploaded.get("original_filename") or file.filename

            if not saved_filename:
                raise RuntimeError("Storage did not return a file URL.")

        except Exception:
            app.logger.exception("Teacher resource upload failed")

            flash(
                "The file could not be uploaded right now. "
                "Please check the storage settings or try again later.",
                "danger"
            )

            return redirect(url_for("upload_resource"))

        teacher_id = teacher["id"] if teacher else None

        try:
            execute_commit("""
                INSERT INTO teacher_resources (
                    school_id,
                    teacher_id,
                    class_name,
                    subject,
                    term,
                    title,
                    resource_type,
                    filename,
                    original_filename,
                    uploaded_by
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
                session.get("full_name") or session.get("username") or "System"
            ))

            log_audit(
                "Uploaded teacher resource",
                "teacher_resources",
                None,
                f"{title} - {class_name} - {subject}"
            )

        except Exception:
            app.logger.exception("Saving teacher resource record failed")

            flash(
                "The file uploaded, but EduTrack could not save its record. "
                "Please contact the administrator.",
                "danger"
            )

            return redirect(url_for("upload_resource"))

        flash("Resource uploaded successfully.", "success")
        return redirect(url_for("teacher_resources"))

    return render_template(
    "upload_resource.html",
    class_options=class_options,
    subjects=subjects,
    role=role
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
    search = request.args.get("search", "").strip()

    query = """
        SELECT
            tr.*,
            t.full_name AS teacher_name
        FROM teacher_resources tr
        LEFT JOIN teachers t ON tr.teacher_id = t.id
        WHERE 1=1
    """

    params = []
    teacher = None
    parent_student = None

    if role != "super_admin":
        query += " AND tr.school_id = ?"
        params.append(school_id)

    # Teachers see resources they uploaded
    if role == "teacher":
        teacher = fetch_one("""
            SELECT *
            FROM teachers
            WHERE user_id = ?
              AND school_id = ?
            LIMIT 1
        """, (user_id, school_id))

        if teacher:
            query += " AND tr.teacher_id = ?"
            params.append(teacher["id"])
        else:
            query += " AND 1=0"

    # Parents see resources for their child's class
    if role == "parent":
        parent_student = fetch_one("""
            SELECT s.*
            FROM students s
            JOIN guardians g ON s.id = g.student_id
            WHERE g.parent_user_id = ?
              AND s.school_id = ?
            ORDER BY s.first_name, s.last_name
            LIMIT 1
        """, (user_id, school_id))

        if parent_student:
            query += " AND tr.class_name = ?"
            params.append(parent_student["class_name"])
        else:
            query += " AND 1=0"

    if search:
        query += """
            AND (
                tr.title LIKE ?
                OR tr.resource_type LIKE ?
                OR tr.subject LIKE ?
                OR tr.uploaded_by LIKE ?
            )
        """
        like = f"%{search}%"
        params.extend([like, like, like, like])

    if class_filter:
        query += " AND tr.class_name = ?"
        params.append(class_filter)

    if subject_filter:
        query += " AND tr.subject = ?"
        params.append(subject_filter)

    if term_filter:
        query += " AND tr.term = ?"
        params.append(term_filter)

    query += " ORDER BY tr.uploaded_at DESC, tr.id DESC"

    resources = fetch_all(query, tuple(params))

    # =====================================================
    # FILTER OPTIONS
    # =====================================================
    option_conditions = []
    option_params = []

    if role != "super_admin":
        option_conditions.append("school_id = ?")
        option_params.append(school_id)

    if role == "teacher" and teacher:
        option_conditions.append("teacher_id = ?")
        option_params.append(teacher["id"])

    if role == "parent" and parent_student:
        option_conditions.append("class_name = ?")
        option_params.append(parent_student["class_name"])

    option_where = ""

    if option_conditions:
        option_where = " WHERE " + " AND ".join(option_conditions)

    class_rows = fetch_all(
        f"""
        SELECT DISTINCT class_name
        FROM teacher_resources
        {option_where}
        {"AND" if option_where else "WHERE"} class_name IS NOT NULL
          AND TRIM(class_name) != ''
        ORDER BY class_name
        """,
        tuple(option_params)
    )

    subject_rows = fetch_all(
        f"""
        SELECT DISTINCT subject
        FROM teacher_resources
        {option_where}
        {"AND" if option_where else "WHERE"} subject IS NOT NULL
          AND TRIM(subject) != ''
        ORDER BY subject
        """,
        tuple(option_params)
    )

    class_options = [row["class_name"] for row in class_rows]
    subjects = [row["subject"] for row in subject_rows]

    return render_template(
        "teacher_resources.html",
        resources=resources,
        class_options=class_options,
        subjects=subjects,
        class_filter=class_filter,
        subject_filter=subject_filter,
        term_filter=term_filter,
        search=search,
        role=role
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