
from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import random
import string
from functools import wraps
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


# =========================================================
# DATABASE HELPERS
# =========================================================
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "school_v2.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_one(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row


def fetch_all(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def execute_commit(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()


# =========================================================
# DATABASE SETUP
# =========================================================
def init_db():
    conn = get_db()
    cursor = conn.cursor()

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

    conn.commit()
    conn.close()


def create_default_school():
    school = fetch_one("SELECT * FROM schools WHERE school_code = ?", ("SCH001",))
    if not school:
        execute_commit(
            "INSERT INTO schools (school_name, school_code) VALUES (?, ?)",
            ("Demo School", "SCH001"),
        )


def create_super_admin():
    admin = fetch_one("SELECT * FROM users WHERE username = ?", ("superadmin",))
    school = fetch_one("SELECT * FROM schools WHERE school_code = ?", ("SCH001",))

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
                elif role == "teacher":
                    return redirect(url_for("teacher_dashboard"))
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


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

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["school_id"] = user["school_id"]
            session["role"] = user["role"]
            session["full_name"] = user["full_name"]

            if user["role"] == "parent":
                return redirect(url_for("parent_dashboard"))
            if user["role"] == "teacher":
                return redirect(url_for("teacher_dashboard"))
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
def dashboard():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        total_schools = fetch_one("SELECT COUNT(*) AS total FROM schools")["total"]
        total_students = fetch_one("SELECT COUNT(*) AS total FROM students")["total"]
        total_teachers = fetch_one("SELECT COUNT(*) AS total FROM teachers")["total"]
        total_users = fetch_one("SELECT COUNT(*) AS total FROM users")["total"]
        total_fee_records = fetch_one("SELECT COUNT(*) AS total FROM fees")["total"]
    else:
        total_schools = 0
        total_students = fetch_one("SELECT COUNT(*) AS total FROM students WHERE school_id = ?", (school_id,))["total"]
        total_teachers = fetch_one("SELECT COUNT(*) AS total FROM teachers WHERE school_id = ?", (school_id,))["total"]
        total_users = fetch_one("SELECT COUNT(*) AS total FROM users WHERE school_id = ?", (school_id,))["total"]
        total_fee_records = fetch_one("SELECT COUNT(*) AS total FROM fees WHERE school_id = ?", (school_id,))["total"]

    return render_template(
        "dashboard.html",
        total_schools=total_schools,
        total_students=total_students,
        total_teachers=total_teachers,
        total_users=total_users,
        total_fee_records=total_fee_records
    )

# =========================================================
# SCHOOL ADMINISTRATION
# =========================================================
@app.route("/schools")
@login_required
@roles_required("super_admin")
def schools():
    school_list = fetch_all("SELECT * FROM schools ORDER BY school_name")
    return render_template("schools.html", schools=school_list)


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

        execute_commit("INSERT INTO schools (school_name, school_code) VALUES (?, ?)", (school_name, school_code))
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


# =========================================================
# STUDENTS
# =========================================================
@app.route("/students")
@login_required
@roles_required("school_admin", "super_admin")
def students():
    school_id = session.get("school_id")
    role = session.get("role")
    search = request.args.get("search", "").strip()

    params = []
    query = "SELECT * FROM students"

    conditions = []
    if role != "super_admin":
        conditions.append("school_id = ?")
        params.append(school_id)

    if search:
        conditions.append("(first_name LIKE ? OR last_name LIKE ? OR student_number LIKE ? OR class_name LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like, like])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY class_name, first_name, last_name"

    students_list = fetch_all(query, tuple(params))

    grouped_students = {}
    for student in students_list:
        class_name = student["class_name"] or "Unassigned Class"
        grouped_students.setdefault(class_name, []).append(student)

    return render_template("students.html", grouped_students=grouped_students, search=search)


@app.route("/add_student")
@login_required
@roles_required("school_admin", "super_admin")
def add_student():
    schools = fetch_all("SELECT * FROM schools ORDER BY school_name")
    return render_template(
        "add_student.html",
        class_options=CLASS_OPTIONS,
        schools=schools
    )

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
        cursor.execute(
            """
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
            """,
            (
                school_id, student_number, first_name, last_name, birthday, gender,
                enrollment_date, leaving_year, class_name, boarding_status,
                home_address, mailing_address, student_phone, medical_info,
                emergency_contact, guardian1_name, guardian1_relationship,
                guardian1_phone, guardian1_whatsapp, guardian1_email,
                guardian2_name, guardian2_relationship, guardian2_phone,
                guardian2_whatsapp, guardian2_email, current_status,
            ),
        )
        student_id = cursor.lastrowid

        parent_user_id = None
        if parent_username:
            existing_parent = cursor.execute("SELECT * FROM users WHERE username = ?", (parent_username,)).fetchone()

            if existing_parent:
                parent_user_id = existing_parent["id"]
            else:
                cursor.execute(
                    """
                    INSERT INTO users (school_id, full_name, username, password, role)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        school_id,
                        guardian1_name or f"{first_name} Parent",
                        parent_username,
                        generate_password_hash(temporary_password),
                        "parent",
                    ),
                )
                parent_user_id = cursor.lastrowid

        if guardian1_name or guardian1_phone:
            cursor.execute(
                """
                INSERT INTO guardians (school_id, student_id, parent_user_id, full_name, relationship, phone, whatsapp, email)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    school_id,
                    student_id,
                    parent_user_id,
                    guardian1_name,
                    guardian1_relationship,
                    guardian1_phone,
                    guardian1_whatsapp,
                    guardian1_email,
                ),
            )

        if guardian2_name or guardian2_phone:
            cursor.execute(
                """
                INSERT INTO guardians (school_id, student_id, parent_user_id, full_name, relationship, phone, whatsapp, email)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    school_id,
                    student_id,
                    parent_user_id,
                    guardian2_name,
                    guardian2_relationship,
                    guardian2_phone,
                    guardian2_whatsapp,
                    guardian2_email,
                ),
            )

        conn.commit()

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
@roles_required("school_admin", "super_admin")
def student_profile(id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (id,))
        guardians = fetch_all("SELECT * FROM guardians WHERE student_id = ?", (id,))
        fees = fetch_all("SELECT * FROM fees WHERE student_id = ? ORDER BY term_name", (id,))
        results = fetch_all("SELECT * FROM results WHERE student_id = ? ORDER BY term, subject", (id,))
        attendance_records = fetch_all("SELECT * FROM attendance WHERE student_id = ? ORDER BY date DESC", (id,))
    else:
        student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (id, school_id))
        if not student:
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("students"))

        guardians = fetch_all("SELECT * FROM guardians WHERE student_id = ? AND school_id = ?", (id, school_id))
        fees = fetch_all("SELECT * FROM fees WHERE student_id = ? AND school_id = ? ORDER BY term_name", (id, school_id))
        results = fetch_all("SELECT * FROM results WHERE student_id = ? AND school_id = ? ORDER BY term, subject", (id, school_id))
        attendance_records = fetch_all("SELECT * FROM attendance WHERE student_id = ? AND school_id = ? ORDER BY date DESC", (id, school_id))

    return render_template(
        "student_profile.html",
        student=student,
        guardians=guardians,
        fees=fees,
        results=results,
        attendance_records=attendance_records,
    )


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
            cursor.execute("DELETE FROM guardians WHERE student_id = ?", (id,))
            cursor.execute("DELETE FROM fees WHERE student_id = ?", (id,))
            cursor.execute("DELETE FROM results WHERE student_id = ?", (id,))
            cursor.execute("DELETE FROM attendance WHERE student_id = ?", (id,))
            cursor.execute("DELETE FROM students WHERE id = ?", (id,))
        else:
            cursor.execute("DELETE FROM guardians WHERE student_id = ? AND school_id = ?", (id, school_id))
            cursor.execute("DELETE FROM fees WHERE student_id = ? AND school_id = ?", (id, school_id))
            cursor.execute("DELETE FROM results WHERE student_id = ? AND school_id = ?", (id, school_id))
            cursor.execute("DELETE FROM attendance WHERE student_id = ? AND school_id = ?", (id, school_id))
            cursor.execute("DELETE FROM students WHERE id = ? AND school_id = ?", (id, school_id))

        conn.commit()
        flash("Student deleted successfully.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Error deleting student: {str(e)}", "danger")

    finally:
        conn.close()

    return redirect(url_for("students"))


@app.route("/student/deactivate/<int:id>", methods=["POST"])
@login_required
@roles_required("school_admin", "super_admin")
def deactivate_student(id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (id,))
    else:
        student = fetch_one("SELECT * FROM students WHERE id = ? AND school_id = ?", (id, school_id))

    if not student:
        flash("Student not found or access denied.", "danger")
        return redirect(url_for("students"))

    execute_commit("UPDATE students SET current_status = ? WHERE id = ?", ("Inactive", id))
    flash("Student deactivated successfully.", "success")
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
            cursor.execute(
                """
                INSERT INTO users (school_id, full_name, username, password, role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (school_id, full_name, username, generate_password_hash(password), "teacher"),
            )
            user_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO teachers (school_id, user_id, teacher_id, full_name, phone, email)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
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
        assignments_list = fetch_all(
            """
            SELECT ta.*, t.full_name
            FROM teacher_assignments ta
            JOIN teachers t ON ta.teacher_id = t.id
            ORDER BY t.full_name, ta.class_name, ta.subject
            """
        )
    else:
        teachers_list = fetch_all("SELECT * FROM teachers WHERE school_id = ? ORDER BY full_name", (school_id,))
        assignments_list = fetch_all(
            """
            SELECT ta.*, t.full_name
            FROM teacher_assignments ta
            JOIN teachers t ON ta.teacher_id = t.id
            WHERE ta.school_id = ?
            ORDER BY t.full_name, ta.class_name, ta.subject
            """,
            (school_id,),
        )

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

    teacher = fetch_one(
        """
        SELECT * FROM teachers
        WHERE user_id = ? AND school_id = ?
        LIMIT 1
        """,
        (user_id, school_id),
    )

    assignments_list = []
    if teacher:
        assignments_list = fetch_all(
            """
            SELECT *
            FROM teacher_assignments
            WHERE teacher_id = ? AND school_id = ?
            ORDER BY class_name, subject
            """,
            (teacher["id"], school_id),
        )

    return render_template("teacher_dashboard.html", teacher=teacher, assignments=assignments_list)


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

    if role == "super_admin":
        students = fetch_all("SELECT * FROM students ORDER BY first_name, last_name")
    else:
        students = fetch_all("SELECT * FROM students WHERE school_id = ? ORDER BY first_name, last_name", (school_id,))

    if request.method == "POST":
        student_id = request.form.get("student_id")
        term_name = request.form.get("term_name")
        amount = float(request.form.get("amount") or 0)
        paid_amount = float(request.form.get("paid_amount") or 0)
        due_date = request.form.get("due_date")
        payment_date = request.form.get("payment_date")
        receipt_number = request.form.get("receipt_number", "").strip()

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
            cursor.execute(
                """
                INSERT INTO fees (school_id, student_id, term_name, amount, paid_amount, balance, status, due_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (school_id, student_id, term_name, amount, paid_amount, balance, status, due_date),
            )
            fee_id = cursor.lastrowid

            if paid_amount > 0:
                cursor.execute(
                    """
                    INSERT INTO fee_payments (school_id, fee_id, payment_date, amount_paid, receipt_number)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (school_id, fee_id, payment_date, paid_amount, receipt_number),
                )

            conn.commit()
            flash("Fee record added successfully.", "success")
            return redirect(url_for("fees"))

        except Exception as e:
            conn.rollback()
            flash(f"Error adding fee: {str(e)}", "danger")
            return redirect(url_for("add_fee"))

        finally:
            conn.close()

    return render_template("add_fee.html", students=students)


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
                "UPDATE fees SET paid_amount = ?, balance = ?, status = ? WHERE id = ?",
                (new_paid_amount, new_balance, status, fee_id),
            )

            cursor.execute(
                """
                INSERT INTO fee_payments (school_id, fee_id, payment_date, amount_paid, receipt_number)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fee["school_id"], fee_id, payment_date, additional_payment, receipt_number),
            )

            conn.commit()
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
        subjects_rows = fetch_all(
            """
            SELECT DISTINCT subject
            FROM teacher_assignments
            WHERE subject IS NOT NULL AND subject != ''
            ORDER BY subject
            """
        )
    else:
        students_list = fetch_all("SELECT * FROM students WHERE school_id = ? ORDER BY first_name, last_name", (school_id,))
        subjects_rows = fetch_all(
            """
            SELECT DISTINCT subject
            FROM teacher_assignments
            WHERE school_id = ? AND subject IS NOT NULL AND subject != ''
            ORDER BY subject
            """,
            (school_id,),
        )

    subjects_list = [row["subject"] for row in subjects_rows]

    return render_template("enter_result.html", class_options=CLASS_OPTIONS, students=students_list, subjects=subjects_list)


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
        result_records = fetch_all(
            """
            SELECT r.*, s.first_name, s.last_name, s.student_number
            FROM results r
            JOIN students s ON r.student_id = s.id
            ORDER BY s.first_name, s.last_name, r.subject
            """
        )
    else:
        result_records = fetch_all(
            """
            SELECT r.*, s.first_name, s.last_name, s.student_number
            FROM results r
            JOIN students s ON r.student_id = s.id
            WHERE r.school_id = ?
            ORDER BY s.first_name, s.last_name, r.subject
            """,
            (school_id,),
        )

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
                """
                INSERT INTO attendance (school_id, student_id, class_name, date, status)
                VALUES (?, ?, ?, ?, ?)
                """,
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
        attendance_list = fetch_all(
            """
            SELECT a.*, s.first_name, s.last_name, s.student_number
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            ORDER BY a.date DESC, s.first_name, s.last_name
            """
        )
    else:
        attendance_list = fetch_all(
            """
            SELECT a.*, s.first_name, s.last_name, s.student_number
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.school_id = ?
            ORDER BY a.date DESC, s.first_name, s.last_name
            """,
            (school_id,),
        )

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
        assignments_list = fetch_all(
            """
            SELECT a.*
            FROM assignments a
            JOIN students s ON a.class_name = s.class_name
            JOIN guardians g ON s.id = g.student_id
            WHERE g.parent_user_id = ? AND a.school_id = ?
            ORDER BY a.due_date ASC, a.class_name ASC, a.subject ASC
            """,
            (user_id, school_id),
        )
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
        subjects_rows = fetch_all(
            """
            SELECT DISTINCT subject
            FROM teacher_assignments
            WHERE subject IS NOT NULL AND subject != ''
            ORDER BY subject
            """
        )
    else:
        subjects_rows = fetch_all(
            """
            SELECT DISTINCT subject
            FROM teacher_assignments
            WHERE school_id = ? AND subject IS NOT NULL AND subject != ''
            ORDER BY subject
            """,
            (school_id,),
        )

    subjects_list = [row["subject"] for row in subjects_rows]

    if request.method == "POST":
        class_name = request.form.get("class_name")
        subject = request.form.get("subject")
        title = request.form.get("title")
        description = request.form.get("description")
        due_date = request.form.get("due_date")

        if not class_name or not subject or not title or not description or not due_date:
            flash("All assignment fields are required.", "danger")
            return redirect(url_for("add_assignment"))

        execute_commit(
            """
            INSERT INTO assignments (school_id, class_name, subject, title, description, due_date, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (school_id, class_name, subject, title, description, due_date, session.get("full_name")),
        )

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

    student = fetch_one(
        """
        SELECT s.*
        FROM students s
        JOIN guardians g ON s.id = g.student_id
        WHERE g.parent_user_id = ? AND s.school_id = ?
        LIMIT 1
        """,
        (user_id, school_id),
    )

    fee_summary = {"total_amount": 0, "total_paid": 0, "total_balance": 0}

    if student:
        fee_summary = fetch_one(
            """
            SELECT
                COALESCE(SUM(amount), 0) AS total_amount,
                COALESCE(SUM(paid_amount), 0) AS total_paid,
                COALESCE(SUM(balance), 0) AS total_balance
            FROM fees
            WHERE student_id = ? AND school_id = ?
            """,
            (student["id"], school_id),
        )

    return render_template("parent_dashboard.html", student=student, fee_summary=fee_summary)


@app.route("/parent_fees")
@login_required
@roles_required("parent")
def parent_fees():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    fee_records = fetch_all(
        """
        SELECT f.*, s.first_name, s.last_name, s.class_name
        FROM fees f
        JOIN guardians g ON f.student_id = g.student_id
        JOIN students s ON s.id = f.student_id
        WHERE g.parent_user_id = ? AND f.school_id = ?
        ORDER BY f.term_name
        """,
        (user_id, school_id),
    )

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

    attendance_list = fetch_all(
        """
        SELECT a.*, s.first_name, s.last_name, s.student_number
        FROM attendance a
        JOIN guardians g ON a.student_id = g.student_id
        JOIN students s ON s.id = a.student_id
        WHERE g.parent_user_id = ? AND a.school_id = ?
        ORDER BY a.date DESC
        """,
        (user_id, school_id),
    )

    return render_template("parent_attendance.html", attendance_records=attendance_list)


@app.route("/parent_assignments")
@login_required
@roles_required("parent")
def parent_assignments():
    school_id = session.get("school_id")
    user_id = session.get("user_id")

    assignments_list = fetch_all(
        """
        SELECT a.*
        FROM assignments a
        JOIN students s ON a.class_name = s.class_name
        JOIN guardians g ON s.id = g.student_id
        WHERE g.parent_user_id = ? AND a.school_id = ?
        ORDER BY a.due_date ASC
        """,
        (user_id, school_id),
    )

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

        user = fetch_one(
            """
            SELECT u.id
            FROM users u
            JOIN guardians g ON u.id = g.parent_user_id
            JOIN students s ON s.id = g.student_id
            WHERE s.student_number = ? AND g.phone = ?
            LIMIT 1
            """,
            (student_number, phone),
        )

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
        teacher = fetch_one(
            """
            SELECT * FROM teachers
            WHERE user_id = ? AND school_id = ?
            LIMIT 1
            """,
            (session["user_id"], school_id),
        )

        timetable_rows = []
        if teacher:
            timetable_rows = fetch_all(
                """
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
                """,
                (school_id, teacher["id"]),
            )

        return render_template("teacher_timetable.html", timetable_rows=timetable_rows)

    if role == "super_admin":
        if selected_class:
            timetable_rows = fetch_all(
                """
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
                """,
                (selected_class,),
            )
        else:
            timetable_rows = []
    else:
        if selected_class:
            timetable_rows = fetch_all(
                """
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
                """,
                (school_id, selected_class),
            )
        else:
            timetable_rows = []

    return render_template(
        "timetable.html",
        class_options=CLASS_OPTIONS,
        selected_class=selected_class,
        timetable_rows=timetable_rows,
    )


@app.route("/add_timetable", methods=["GET", "POST"])
@login_required
@roles_required("school_admin", "super_admin")
def add_timetable():
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        teachers_list = fetch_all("SELECT * FROM teachers ORDER BY full_name")
        subjects_rows = fetch_all(
            """
            SELECT DISTINCT subject
            FROM teacher_assignments
            WHERE subject IS NOT NULL AND subject != ''
            ORDER BY subject
            """
        )
    else:
        teachers_list = fetch_all("SELECT * FROM teachers WHERE school_id = ? ORDER BY full_name", (school_id,))
        subjects_rows = fetch_all(
            """
            SELECT DISTINCT subject
            FROM teacher_assignments
            WHERE school_id = ? AND subject IS NOT NULL AND subject != ''
            ORDER BY subject
            """,
            (school_id,),
        )

    subjects = [row["subject"] for row in subjects_rows]

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
            teacher_conflict = fetch_one(
                """
                SELECT * FROM timetables
                WHERE teacher_id = ?
                  AND day_of_week = ?
                  AND start_time < ?
                  AND end_time > ?
                """,
                (teacher_id, day_of_week, end_time, start_time),
            )
            class_conflict = fetch_one(
                """
                SELECT * FROM timetables
                WHERE class_name = ?
                  AND day_of_week = ?
                  AND start_time < ?
                  AND end_time > ?
                """,
                (class_name, day_of_week, end_time, start_time),
            )
        else:
            teacher_conflict = fetch_one(
                """
                SELECT * FROM timetables
                WHERE school_id = ?
                  AND teacher_id = ?
                  AND day_of_week = ?
                  AND start_time < ?
                  AND end_time > ?
                """,
                (school_id, teacher_id, day_of_week, end_time, start_time),
            )
            class_conflict = fetch_one(
                """
                SELECT * FROM timetables
                WHERE school_id = ?
                  AND class_name = ?
                  AND day_of_week = ?
                  AND start_time < ?
                  AND end_time > ?
                """,
                (school_id, class_name, day_of_week, end_time, start_time),
            )

        if teacher_conflict:
            flash("This teacher is already assigned during that time.", "danger")
            return redirect(url_for("add_timetable"))

        if class_conflict:
            flash("This class already has a lesson during that time.", "danger")
            return redirect(url_for("add_timetable"))

        execute_commit(
            """
            INSERT INTO timetables (
                school_id, class_name, subject, teacher_id,
                day_of_week, start_time, end_time, room
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (school_id, class_name, subject, teacher_id, day_of_week, start_time, end_time, room),
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
@app.route("/send_fee_reminder/<int:student_id>")
@login_required
@roles_required("school_admin", "super_admin")
def send_fee_reminder(student_id):
    school_id = session.get("school_id")
    role = session.get("role")

    if role == "super_admin":
        student = fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
    else:
        student = fetch_one(
            "SELECT * FROM students WHERE id = ? AND school_id = ?",
            (student_id, school_id)
        )

    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("students"))

    # Calculate total balance
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

    # WhatsApp format (remove spaces, add country code manually if needed)
    phone = phone.replace(" ", "")

    message = f"""
Dear Parent,

This is a reminder that {student['first_name']} {student['last_name']} has an outstanding school fee balance of ${balance}.

Please make payment as soon as possible.

Thank you.
""".strip()

    import urllib.parse
    encoded_message = urllib.parse.quote(message)

    whatsapp_link = f"https://wa.me/{phone}?text={encoded_message}"

    return redirect(whatsapp_link)

#with app.app_context():
 #   init_db()
  #  create_default_school()
   # create_super_admin()

def setup_app():
    try:
        print("Starting setup...")

        with app.app_context():
            init_db()
            print("DB initialized")

            create_default_school()
            print("School created")

            create_super_admin()
            print("Admin created")

        print("Setup complete")

    except Exception as e:
        print("SETUP ERROR:", e)

setup_app()
if __name__ == "__main__":
    app.run(debug=True)
