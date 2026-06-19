from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
import pandas as pd

from utils.auth import login_required, roles_required
from utils.db import fetch_one, fetch_all, execute_commit, get_db, convert_query, is_postgres
from utils.audit import log_audit
from utils.helpers import generate_teacher_id


def register_teacher_routes(app):

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
                    cursor.execute(convert_query("""
                        INSERT INTO users (school_id, full_name, username, password, role)
                        VALUES (?, ?, ?, ?, ?)
                        RETURNING id
                    """), (school_id, full_name, username, generate_password_hash(password), "teacher"))
                    user_id = cursor.fetchone()["id"]
                else:
                    cursor.execute(convert_query("""
                        INSERT INTO users (school_id, full_name, username, password, role)
                        VALUES (?, ?, ?, ?, ?)
                    """), (school_id, full_name, username, generate_password_hash(password), "teacher"))
                    user_id = cursor.lastrowid

                cursor.execute(convert_query("""
                    INSERT INTO teachers (school_id, user_id, teacher_id, full_name, phone, email)
                    VALUES (?, ?, ?, ?, ?, ?)
                """), (school_id, user_id, generate_teacher_id(), full_name, phone, email))

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
        schools = fetch_all("SELECT * FROM schools ORDER BY school_name") if role == "super_admin" else []

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
        role = session.get("role")

        if role == "super_admin":
            teacher = fetch_one("SELECT * FROM teachers WHERE id = ?", (teacher_id,))
        else:
            teacher = fetch_one("""
                SELECT *
                FROM teachers
                WHERE id = ?
                  AND school_id = ?
            """, (teacher_id, school_id))

        if not teacher:
            flash("Teacher not found.", "danger")
            return redirect(url_for("teachers"))

        return render_template("edit_teacher.html", teacher=teacher)


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

        log_audit("Updated teacher", "teachers", teacher_id, f"Updated teacher {full_name}")

        flash("Teacher updated successfully.", "success")
        return redirect(url_for("teachers"))


    @app.route("/deactivate_teacher/<int:teacher_id>", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def deactivate_teacher(teacher_id):
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            teacher = fetch_one("SELECT * FROM teachers WHERE id = ?", (teacher_id,))
        else:
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
            execute_commit("UPDATE users SET is_active = 0 WHERE id = ?", (teacher["user_id"],))

        log_audit("Deactivated teacher", "teachers", teacher_id, f"Deactivated teacher {teacher['full_name']}")

        flash("Teacher deactivated successfully.", "success")
        return redirect(url_for("teachers"))


    @app.route("/activate_teacher/<int:teacher_id>", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def activate_teacher(teacher_id):
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            teacher = fetch_one("SELECT * FROM teachers WHERE id = ?", (teacher_id,))
        else:
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
            execute_commit("UPDATE users SET is_active = 1 WHERE id = ?", (teacher["user_id"],))

        log_audit("Activated teacher", "teachers", teacher_id, f"Activated teacher {teacher['full_name']}")

        flash("Teacher activated successfully.", "success")
        return redirect(url_for("teachers"))


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
                            cursor.execute(convert_query("""
                                INSERT INTO users (school_id, full_name, username, password, role)
                                VALUES (?, ?, ?, ?, ?)
                            """), (
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

                flash(f"Teacher import complete. Imported: {imported}, Skipped: {skipped}", "success")
                return redirect(url_for("teachers"))

            except Exception as e:
                flash(f"Import failed: {str(e)}", "danger")
                return redirect(url_for("import_teachers"))

        return render_template("import_teachers.html", schools=schools)
    

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