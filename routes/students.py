from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
import random
import string

from utils.db import (
    get_db, is_postgres, convert_query,
    fetch_one, fetch_all, execute_commit
)

from utils.auth import login_required, roles_required
from utils.audit import log_audit
from utils.helpers import (
    CLASS_OPTIONS,
    generate_student_number,
    row_get
)


def delete_by_scope(cursor, query, params):
    cursor.execute(convert_query(query), params)


def register_student_routes(app):

    @app.route("/students")
    @login_required
    @roles_required("super_admin", "school_admin")
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

        students_list = fetch_all(query, tuple(params))
        return render_template("students.html", students=students_list, search=search)


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
        role = session.get("role")

        if role == "super_admin":
            school_id = request.form.get("school_id")
        else:
            school_id = session.get("school_id")

        if not school_id:
            flash("Please select a school.", "danger")
            return redirect(url_for("add_student"))

        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        birthday = request.form.get("birthday", "").strip()
        gender = request.form.get("gender", "").strip()
        enrollment_date = request.form.get("enrollment_date", "").strip()
        leaving_year = request.form.get("leaving_year", "").strip()
        class_name = request.form.get("class_name", "").strip()
        boarding_status = request.form.get("boarding_status", "").strip()
        home_address = request.form.get("home_address", "").strip()
        mailing_address = request.form.get("mailing_address", "").strip()
        student_phone = request.form.get("student_phone", "").strip()
        medical_info = request.form.get("medical_info", "").strip()
        emergency_contact = request.form.get("emergency_contact", "").strip()

        guardian1_name = request.form.get("guardian1_name", "").strip()
        guardian1_relationship = request.form.get("guardian1_relationship", "").strip()
        guardian1_phone = request.form.get("guardian1_phone", "").strip()
        guardian1_whatsapp = request.form.get("guardian1_whatsapp", "").strip()
        guardian1_email = request.form.get("guardian1_email", "").strip()

        guardian2_name = request.form.get("guardian2_name", "").strip()
        guardian2_relationship = request.form.get("guardian2_relationship", "").strip()
        guardian2_phone = request.form.get("guardian2_phone", "").strip()
        guardian2_whatsapp = request.form.get("guardian2_whatsapp", "").strip()
        guardian2_email = request.form.get("guardian2_email", "").strip()

        current_status = request.form.get("current_status", "Active").strip() or "Active"
        parent_username = request.form.get("parent_username", "").strip() or guardian1_phone

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
                existing_parent = fetch_one(
                    "SELECT * FROM users WHERE username = ?",
                    (parent_username,)
                )

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
                                "parent"
                            )
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
                            "parent"
                        ))
                        parent_user_id = cursor.lastrowid

            if guardian1_name or guardian1_phone:
                cursor.execute(
                    convert_query("""
                        INSERT INTO guardians (
                            school_id, student_id, parent_user_id, full_name,
                            relationship, phone, whatsapp, email
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """),
                    (
                        school_id, student_id, parent_user_id, guardian1_name,
                        guardian1_relationship, guardian1_phone,
                        guardian1_whatsapp, guardian1_email
                    )
                )

            if guardian2_name or guardian2_phone:
                cursor.execute(
                    convert_query("""
                        INSERT INTO guardians (
                            school_id, student_id, parent_user_id, full_name,
                            relationship, phone, whatsapp, email
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """),
                    (
                        school_id, student_id, parent_user_id, guardian2_name,
                        guardian2_relationship, guardian2_phone,
                        guardian2_whatsapp, guardian2_email
                    )
                )

            if is_postgres():
                cursor.execute(
                    convert_query("""
                        INSERT INTO school_classes (school_id, class_name)
                        VALUES (?, ?)
                        ON CONFLICT (school_id, class_name) DO NOTHING
                    """),
                    (school_id, class_name)
                )
            else:
                cursor.execute("""
                    INSERT OR IGNORE INTO school_classes (school_id, class_name)
                    VALUES (?, ?)
                """, (school_id, class_name))

            conn.commit()

            log_audit(
                "Added student",
                "students",
                student_id,
                f"Added {first_name} {last_name} - {student_number}"
            )

            if parent_username and parent_user_id:
                flash(
                    f"Student added successfully. Student Number: {student_number}. "
                    f"Parent username: {parent_username}. Temporary password: {temporary_password}",
                    "success"
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
            student = fetch_one(
                "SELECT * FROM students WHERE id = ? AND school_id = ?",
                (id, school_id)
            )

        if not student:
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("students"))

        return render_template(
            "edit_student.html",
            student=student,
            class_options=CLASS_OPTIONS
        )


    @app.route("/update_student/<int:id>", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def update_student(id):
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            student = fetch_one("SELECT * FROM students WHERE id = ?", (id,))
        else:
            student = fetch_one(
                "SELECT * FROM students WHERE id = ? AND school_id = ?",
                (id, school_id)
            )

        if not student:
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("students"))

        execute_commit("""
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
        """, (
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
        ))

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
            student = fetch_one(
                "SELECT * FROM students WHERE id = ? AND school_id = ?",
                (id, school_id)
            )

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

            log_audit(
                "Deleted student",
                "students",
                id,
                f"Deleted student ID {id}"
            )

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
            student = fetch_one(
                "SELECT * FROM students WHERE id = ? AND school_id = ?",
                (id, school_id)
            )

        if not student:
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("students"))

        execute_commit("UPDATE students SET current_status = ? WHERE id = ?", ("Active", id))

        log_audit(
            "Activated student",
            "students",
            id,
            f"Activated student ID {id}"
        )

        flash("Student activated successfully.", "success")
        return redirect(url_for("students"))


    @app.route("/deactivate_student/<int:student_id>", methods=["POST"])
    @login_required
    @roles_required("super_admin", "school_admin")
    def deactivate_student(student_id):
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
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("students"))

        execute_commit(
            "UPDATE students SET current_status = ? WHERE id = ?",
            ("Inactive", student_id)
        )

        log_audit(
            "Deactivated student",
            "students",
            student_id,
            "Student status changed to Inactive"
        )

        flash("Student deactivated successfully.", "success")
        return redirect(url_for("students"))


    @app.route("/reactivate_student/<int:student_id>", methods=["POST"])
    @login_required
    @roles_required("super_admin", "school_admin")
    def reactivate_student(student_id):
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
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("students"))

        execute_commit(
            "UPDATE students SET current_status = ? WHERE id = ?",
            ("Active", student_id)
        )

        log_audit(
            "Reactivated student",
            "students",
            student_id,
            "Student status changed to Active"
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
            students_list = fetch_all("""
                SELECT *
                FROM students
                ORDER BY class_name, first_name, last_name
            """)
        else:
            students_list = fetch_all("""
                SELECT *
                FROM students
                WHERE school_id = ?
                ORDER BY class_name, first_name, last_name
            """, (school_id,))

        return render_template("print_all_students.html", students=students_list)


    @app.route("/print_class_list/<class_name>")
    @login_required
    @roles_required("school_admin", "super_admin", "teacher")
    def print_class_list(class_name):
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            students_list = fetch_all("""
                SELECT *
                FROM students
                WHERE class_name = ?
                ORDER BY first_name, last_name
            """, (class_name,))
        else:
            students_list = fetch_all("""
                SELECT *
                FROM students
                WHERE school_id = ? AND class_name = ?
                ORDER BY first_name, last_name
            """, (school_id, class_name))

        return render_template(
            "print_class_list.html",
            students=students_list,
            class_name=class_name
        )


    @app.route("/student_progress/<int:student_id>")
    @login_required
    @roles_required("school_admin", "super_admin", "teacher", "parent")
    def student_progress(student_id):
        school_id = session.get("school_id")
        role = session.get("role")
        selected_term = request.args.get("term", "Term 1")

        if role == "parent":
            student = fetch_one("""
                SELECT s.*
                FROM students s
                JOIN guardians g ON s.id = g.student_id
                WHERE s.id = ?
                  AND g.parent_user_id = ?
                  AND s.school_id = ?
            """, (student_id, session.get("user_id"), school_id))
        elif role == "super_admin":
            student = fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        else:
            student = fetch_one(
                "SELECT * FROM students WHERE id = ? AND school_id = ?",
                (student_id, school_id)
            )

        if not student:
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("dashboard"))

        assessments = fetch_all("""
            SELECT *
            FROM assessments
            WHERE student_id = ?
              AND term = ?
            ORDER BY subject, date DESC
        """, (student_id, selected_term))

        subjects = {}

        for a in assessments:
            subject = a["subject"] or "Unknown"

            if subject not in subjects:
                subjects[subject] = {
                    "records": [],
                    "total_percentage": 0,
                    "count": 0,
                    "average": 0
                }

            subjects[subject]["records"].append(a)
            subjects[subject]["total_percentage"] += float(a["percentage"] or 0)
            subjects[subject]["count"] += 1

        overall_total = 0
        subject_count = 0

        for subject, data in subjects.items():
            if data["count"] > 0:
                data["average"] = round(data["total_percentage"] / data["count"], 1)
                overall_total += data["average"]
                subject_count += 1

        overall_average = round(overall_total / subject_count, 1) if subject_count > 0 else 0

        if overall_average >= 80:
            progress_status = "Excellent Progress"
        elif overall_average >= 70:
            progress_status = "Good Progress"
        elif overall_average >= 60:
            progress_status = "Satisfactory Progress"
        elif overall_average >= 50:
            progress_status = "Needs Improvement"
        else:
            progress_status = "Serious Support Needed"

        return render_template(
            "student_progress.html",
            student=student,
            selected_term=selected_term,
            subjects=subjects,
            overall_average=overall_average,
            progress_status=progress_status
        )