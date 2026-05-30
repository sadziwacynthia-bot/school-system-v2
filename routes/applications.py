import os
import random
from datetime import datetime

from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename

from utils.db import (
    get_db,
    is_postgres,
    convert_query,
    fetch_one,
    fetch_all,
    execute_commit
)

from utils.auth import login_required, roles_required
from utils.audit import log_audit
from utils.helpers import CLASS_OPTIONS, generate_student_number


APPLICATION_UPLOAD_FOLDER = os.path.join("static", "uploads", "applications")

ALLOWED_APPLICATION_EXTENSIONS = {
    "pdf", "doc", "docx",
    "png", "jpg", "jpeg"
}

os.makedirs(APPLICATION_UPLOAD_FOLDER, exist_ok=True)


def allowed_application_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_APPLICATION_EXTENSIONS
    )


def save_application_file(file, school_id, label):
    if not file or not file.filename:
        return ""

    if not allowed_application_file(file.filename):
        return ""

    original_name = secure_filename(file.filename)
    ext = original_name.rsplit(".", 1)[1].lower()

    saved_name = (
        f"application_{school_id}_{label}_"
        f"{datetime.now().strftime('%Y%m%d%H%M%S')}_"
        f"{random.randint(1000, 9999)}.{ext}"
    )

    file_path = os.path.join(APPLICATION_UPLOAD_FOLDER, saved_name)
    file.save(file_path)

    return f"uploads/applications/{saved_name}"


def run_waiting_list_migration():
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS waiting_list (
                    id SERIAL PRIMARY KEY,
                    school_id INTEGER,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    gender VARCHAR(20),
                    date_of_birth VARCHAR(50),
                    guardian_name VARCHAR(255),
                    guardian_phone VARCHAR(50),
                    guardian_email VARCHAR(255),
                    applied_class VARCHAR(100),
                    applied_year VARCHAR(20),
                    status VARCHAR(50) DEFAULT 'Pending',
                    notes TEXT,
                    birth_certificate_file TEXT,
                    latest_results_file TEXT,
                    other_document_file TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("ALTER TABLE waiting_list ADD COLUMN IF NOT EXISTS birth_certificate_file TEXT")
            cursor.execute("ALTER TABLE waiting_list ADD COLUMN IF NOT EXISTS latest_results_file TEXT")
            cursor.execute("ALTER TABLE waiting_list ADD COLUMN IF NOT EXISTS other_document_file TEXT")

        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS waiting_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_id INTEGER,
                    first_name TEXT,
                    last_name TEXT,
                    gender TEXT,
                    date_of_birth TEXT,
                    guardian_name TEXT,
                    guardian_phone TEXT,
                    guardian_email TEXT,
                    applied_class TEXT,
                    applied_year TEXT,
                    status TEXT DEFAULT 'Pending',
                    notes TEXT,
                    birth_certificate_file TEXT,
                    latest_results_file TEXT,
                    other_document_file TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            for stmt in [
                "ALTER TABLE waiting_list ADD COLUMN birth_certificate_file TEXT",
                "ALTER TABLE waiting_list ADD COLUMN latest_results_file TEXT",
                "ALTER TABLE waiting_list ADD COLUMN other_document_file TEXT",
            ]:
                try:
                    cursor.execute(stmt)
                except Exception:
                    pass

        conn.commit()
        print("Waiting list migration completed")

    finally:
        conn.close()


def register_application_routes(app):

    @app.route("/applications")
    @login_required
    @roles_required("school_admin", "super_admin")
    def applications():
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            applications_list = fetch_all("""
                SELECT wl.*, s.school_name
                FROM waiting_list wl
                LEFT JOIN schools s ON wl.school_id = s.id
                ORDER BY wl.created_at DESC
            """)
        else:
            applications_list = fetch_all("""
                SELECT *
                FROM waiting_list
                WHERE school_id = ?
                ORDER BY created_at DESC
            """, (school_id,))

        return render_template(
            "applications.html",
            applications=applications_list
        )


    @app.route("/add_application", methods=["GET", "POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def add_application():
        school_id = session.get("school_id")
        role = session.get("role")

        schools = []

        if role == "super_admin":
            schools = fetch_all("""
                SELECT *
                FROM schools
                ORDER BY school_name
            """)

        if request.method == "POST":

            if role == "super_admin":
                school_id = request.form.get("school_id")

            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            gender = request.form.get("gender", "").strip()
            date_of_birth = request.form.get("date_of_birth", "").strip()

            guardian_name = request.form.get("guardian_name", "").strip()
            guardian_phone = request.form.get("guardian_phone", "").strip()
            guardian_email = request.form.get("guardian_email", "").strip()

            applied_class = request.form.get("applied_class", "").strip()
            applied_year = request.form.get("applied_year", "").strip()
            notes = request.form.get("notes", "").strip()

            if not school_id:
                flash("School is required.", "danger")
                return redirect(url_for("add_application"))

            if not first_name or not last_name:
                flash("Student name is required.", "danger")
                return redirect(url_for("add_application"))

            if not applied_class:
                flash("Applied class is required.", "danger")
                return redirect(url_for("add_application"))

            if not applied_year:
                flash("Applied year is required.", "danger")
                return redirect(url_for("add_application"))

            birth_certificate_file = save_application_file(
                request.files.get("birth_certificate_file"),
                school_id,
                "birth_certificate"
            )

            latest_results_file = save_application_file(
                request.files.get("latest_results_file"),
                school_id,
                "latest_results"
            )

            other_document_file = save_application_file(
                request.files.get("other_document_file"),
                school_id,
                "other_document"
            )

            execute_commit("""
                INSERT INTO waiting_list (
                    school_id,
                    first_name,
                    last_name,
                    gender,
                    date_of_birth,
                    guardian_name,
                    guardian_phone,
                    guardian_email,
                    applied_class,
                    applied_year,
                    status,
                    notes,
                    birth_certificate_file,
                    latest_results_file,
                    other_document_file
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                school_id,
                first_name,
                last_name,
                gender,
                date_of_birth,
                guardian_name,
                guardian_phone,
                guardian_email,
                applied_class,
                applied_year,
                "Pending",
                notes,
                birth_certificate_file,
                latest_results_file,
                other_document_file
            ))

            log_audit(
                "Added application",
                "waiting_list",
                None,
                f"Added application for {first_name} {last_name}"
            )

            flash("Application submitted successfully.", "success")
            return redirect(url_for("applications"))

        return render_template(
            "add_application.html",
            schools=schools,
            class_options=CLASS_OPTIONS,
            current_year=datetime.now().year
        )


    @app.route("/approve_application/<int:application_id>", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def approve_application(application_id):
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            application = fetch_one(
                "SELECT * FROM waiting_list WHERE id = ?",
                (application_id,)
            )
        else:
            application = fetch_one(
                "SELECT * FROM waiting_list WHERE id = ? AND school_id = ?",
                (application_id, school_id)
            )

        if not application:
            flash("Application not found.", "danger")
            return redirect(url_for("applications"))

        execute_commit(
            "UPDATE waiting_list SET status = ? WHERE id = ?",
            ("Approved", application_id)
        )

        log_audit(
            "Approved application",
            "waiting_list",
            application_id,
            f"Approved application for {application['first_name']} {application['last_name']}"
        )

        flash("Application approved successfully.", "success")
        return redirect(url_for("applications"))


    @app.route("/reject_application/<int:application_id>", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def reject_application(application_id):
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            application = fetch_one(
                "SELECT * FROM waiting_list WHERE id = ?",
                (application_id,)
            )
        else:
            application = fetch_one(
                "SELECT * FROM waiting_list WHERE id = ? AND school_id = ?",
                (application_id, school_id)
            )

        if not application:
            flash("Application not found.", "danger")
            return redirect(url_for("applications"))

        execute_commit(
            "UPDATE waiting_list SET status = ? WHERE id = ?",
            ("Rejected", application_id)
        )

        log_audit(
            "Rejected application",
            "waiting_list",
            application_id,
            f"Rejected application for {application['first_name']} {application['last_name']}"
        )

        flash("Application rejected.", "success")
        return redirect(url_for("applications"))


    @app.route("/enroll_application/<int:application_id>", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def enroll_application(application_id):
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            application = fetch_one(
                "SELECT * FROM waiting_list WHERE id = ?",
                (application_id,)
            )
        else:
            application = fetch_one(
                "SELECT * FROM waiting_list WHERE id = ? AND school_id = ?",
                (application_id, school_id)
            )

        if not application:
            flash("Application not found.", "danger")
            return redirect(url_for("applications"))

        if application["status"] == "Enrolled":
            flash("This application has already been enrolled.", "warning")
            return redirect(url_for("applications"))

        student_number = generate_student_number()
        app_school_id = application["school_id"]

        conn = get_db()
        cursor = conn.cursor()

        try:
            if is_postgres():
                cursor.execute(
                    convert_query("""
                        INSERT INTO students (
                            school_id, student_number, first_name, last_name,
                            birthday, gender, class_name, guardian1_name,
                            guardian1_phone, guardian1_email, current_status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        RETURNING id
                    """),
                    (
                        app_school_id,
                        student_number,
                        application["first_name"],
                        application["last_name"],
                        application["date_of_birth"],
                        application["gender"],
                        application["applied_class"],
                        application["guardian_name"],
                        application["guardian_phone"],
                        application["guardian_email"],
                        "Active"
                    )
                )
                student_id = cursor.fetchone()["id"]

            else:
                cursor.execute(
                    convert_query("""
                        INSERT INTO students (
                            school_id, student_number, first_name, last_name,
                            birthday, gender, class_name, guardian1_name,
                            guardian1_phone, guardian1_email, current_status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """),
                    (
                        app_school_id,
                        student_number,
                        application["first_name"],
                        application["last_name"],
                        application["date_of_birth"],
                        application["gender"],
                        application["applied_class"],
                        application["guardian_name"],
                        application["guardian_phone"],
                        application["guardian_email"],
                        "Active"
                    )
                )
                student_id = cursor.lastrowid

            if is_postgres():
                cursor.execute(
                    convert_query("""
                        INSERT INTO school_classes (school_id, class_name)
                        VALUES (?, ?)
                        ON CONFLICT (school_id, class_name) DO NOTHING
                    """),
                    (app_school_id, application["applied_class"])
                )
            else:
                cursor.execute("""
                    INSERT OR IGNORE INTO school_classes (school_id, class_name)
                    VALUES (?, ?)
                """, (app_school_id, application["applied_class"]))

            cursor.execute(
                convert_query("""
                    UPDATE waiting_list
                    SET status = ?
                    WHERE id = ?
                """),
                ("Enrolled", application_id)
            )

            conn.commit()

            log_audit(
                "Enrolled application",
                "waiting_list",
                application_id,
                f"Enrolled {application['first_name']} {application['last_name']} as {student_number}"
            )

            flash(
                f"Student enrolled successfully. Student Number: {student_number}",
                "success"
            )

            return redirect(url_for("student_profile", id=student_id))

        except Exception as e:
            conn.rollback()
            flash(f"Error enrolling student: {str(e)}", "danger")
            return redirect(url_for("applications"))

        finally:
            conn.close()


    @app.route("/fix_waiting_list_table")
    @login_required
    @roles_required("super_admin")
    def fix_waiting_list_table():
        run_waiting_list_migration()
        flash("Waiting list table created successfully.", "success")
        return redirect(url_for("applications"))