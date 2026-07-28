from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
from secrets import choice
from string import ascii_letters, digits

from utils.auth import login_required, roles_required
from utils.db import fetch_one, fetch_all, execute_commit
from utils.audit import log_audit


def register_parent_routes(app):

    def current_school_scope():
        return session.get("school_id"), session.get("role")

    def get_parent_or_none(parent_id):
        school_id, role = current_school_scope()

        if role == "super_admin":
            return fetch_one(
                "SELECT * FROM users WHERE id = ? AND role = ?",
                (parent_id, "parent")
            )

        return fetch_one(
            """
            SELECT *
            FROM users
            WHERE id = ?
              AND school_id = ?
              AND role = ?
            """,
            (parent_id, school_id, "parent")
        )

    def get_student_or_none(student_id):
        school_id, role = current_school_scope()

        if role == "super_admin":
            return fetch_one(
                "SELECT * FROM students WHERE id = ?",
                (student_id,)
            )

        return fetch_one(
            "SELECT * FROM students WHERE id = ? AND school_id = ?",
            (student_id, school_id)
        )

    def audit(action, table_name, record_id, details):
        try:
            log_audit(action, table_name, record_id, details)
        except Exception:
            app.logger.exception("Parent-management audit log failed.")

    def generate_temporary_password(length=10):
        alphabet = ascii_letters + digits
        return "".join(choice(alphabet) for _ in range(length))

    @app.route("/parents")
    @login_required
    @roles_required("school_admin", "super_admin")
    def parents():
        school_id, role = current_school_scope()

        search = request.args.get("search", "").strip()
        status = request.args.get("status", "").strip()
        class_name = request.args.get("class_name", "").strip()

        try:
            page = max(int(request.args.get("page", 1)), 1)
        except (TypeError, ValueError):
            page = 1

        per_page = 20
        offset = (page - 1) * per_page

        where = ["u.role = ?"]
        params = ["parent"]

        if role != "super_admin":
            where.append("u.school_id = ?")
            params.append(school_id)

        if search:
            like = f"%{search}%"
            where.append(
                """
                (
                    u.full_name LIKE ?
                    OR u.username LIKE ?
                    OR st.first_name LIKE ?
                    OR st.last_name LIKE ?
                    OR st.student_number LIKE ?
                )
                """
            )
            params.extend([like, like, like, like, like])

        if status == "active":
            where.append("COALESCE(u.is_active, 1) = 1")
        elif status == "inactive":
            where.append("COALESCE(u.is_active, 1) = 0")

        if class_name:
            where.append("st.class_name = ?")
            params.append(class_name)

        where_sql = " AND ".join(where)

        count_row = fetch_one(
            f"""
            SELECT COUNT(DISTINCT u.id) AS total
            FROM users u
            LEFT JOIN guardians g ON g.parent_user_id = u.id
            LEFT JOIN students st ON st.id = g.student_id
            WHERE {where_sql}
            """,
            tuple(params)
        )
        total = int(count_row["total"] or 0) if count_row else 0
        total_pages = max((total + per_page - 1) // per_page, 1)

        if page > total_pages:
            page = total_pages
            offset = (page - 1) * per_page

        parent_rows = fetch_all(
            f"""
            SELECT
                u.id,
                u.school_id,
                u.full_name,
                u.username,
                COALESCE(u.is_active, 1) AS is_active,
                s.school_name,
                COUNT(DISTINCT g.student_id) AS children_count
            FROM users u
            LEFT JOIN schools s ON s.id = u.school_id
            LEFT JOIN guardians g ON g.parent_user_id = u.id
            LEFT JOIN students st ON st.id = g.student_id
            WHERE {where_sql}
            GROUP BY
                u.id,
                u.school_id,
                u.full_name,
                u.username,
                u.is_active,
                s.school_name
            ORDER BY u.full_name
            LIMIT ? OFFSET ?
            """,
            tuple(params + [per_page, offset])
        )

        parent_list = []
        for parent in parent_rows:
            children = fetch_all(
                """
                SELECT
                    st.id,
                    st.first_name,
                    st.last_name,
                    st.student_number,
                    st.class_name
                FROM guardians g
                JOIN students st ON st.id = g.student_id
                WHERE g.parent_user_id = ?
                ORDER BY st.class_name, st.first_name, st.last_name
                """,
                (parent["id"],)
            )

            parent_list.append({
                "id": parent["id"],
                "school_id": parent["school_id"],
                "school_name": parent["school_name"],
                "full_name": parent["full_name"],
                "username": parent["username"],
                "is_active": parent["is_active"],
                "children_count": parent["children_count"],
                "children": children
            })

        stats_params = []
        stats_scope = ""
        if role != "super_admin":
            stats_scope = " AND school_id = ?"
            stats_params.append(school_id)

        total_parents = fetch_one(
            f"SELECT COUNT(*) AS total FROM users WHERE role = 'parent'{stats_scope}",
            tuple(stats_params)
        )["total"]

        active_parents = fetch_one(
            f"""
            SELECT COUNT(*) AS total
            FROM users
            WHERE role = 'parent'
              AND COALESCE(is_active, 1) = 1
              {stats_scope}
            """,
            tuple(stats_params)
        )["total"]

        inactive_parents = fetch_one(
            f"""
            SELECT COUNT(*) AS total
            FROM users
            WHERE role = 'parent'
              AND COALESCE(is_active, 1) = 0
              {stats_scope}
            """,
            tuple(stats_params)
        )["total"]

        linked_students_query = """
            SELECT COUNT(DISTINCT g.student_id) AS total
            FROM guardians g
            JOIN users u ON u.id = g.parent_user_id
            WHERE u.role = 'parent'
        """
        linked_params = []
        if role != "super_admin":
            linked_students_query += " AND u.school_id = ?"
            linked_params.append(school_id)

        linked_students = fetch_one(
            linked_students_query,
            tuple(linked_params)
        )["total"]

        classes_query = "SELECT DISTINCT class_name FROM students WHERE class_name IS NOT NULL"
        classes_params = []
        if role != "super_admin":
            classes_query += " AND school_id = ?"
            classes_params.append(school_id)
        classes_query += " ORDER BY class_name"
        classes = fetch_all(classes_query, tuple(classes_params))

        return render_template(
            "parents.html",
            parents=parent_list,
            search=search,
            status=status,
            class_name=class_name,
            classes=classes,
            total_parents=total_parents,
            active_parents=active_parents,
            inactive_parents=inactive_parents,
            linked_students=linked_students,
            page=page,
            total_pages=total_pages,
            total_results=total
        )

    @app.route("/parents/add", methods=["GET", "POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def add_parent():
        school_id, role = current_school_scope()

        schools = []
        if role == "super_admin":
            schools = fetch_all(
                "SELECT id, school_name FROM schools ORDER BY school_name"
            )

        selected_school_id = school_id
        if role == "super_admin":
            selected_school_id = request.form.get("school_id", type=int)

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            student_ids = request.form.getlist("student_ids")

            if not selected_school_id:
                flash("Please select a school.", "danger")
                return redirect(url_for("add_parent"))

            if not full_name or not username or not password:
                flash("Full name, username, and password are required.", "danger")
                return redirect(url_for("add_parent"))

            if len(password) < 8:
                flash("Password must contain at least 8 characters.", "danger")
                return redirect(url_for("add_parent"))

            existing = fetch_one(
                "SELECT id FROM users WHERE username = ?",
                (username,)
            )
            if existing:
                flash("That username already exists.", "danger")
                return redirect(url_for("add_parent"))

            execute_commit(
                """
                INSERT INTO users
                    (school_id, full_name, username, password, role, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    selected_school_id,
                    full_name,
                    username,
                    generate_password_hash(password),
                    "parent",
                    1
                )
            )

            parent = fetch_one(
                "SELECT id FROM users WHERE username = ?",
                (username,)
            )
            parent_id = parent["id"]

            linked = 0
            for raw_student_id in student_ids:
                try:
                    student_id = int(raw_student_id)
                except (TypeError, ValueError):
                    continue

                student = fetch_one(
                    "SELECT id FROM students WHERE id = ? AND school_id = ?",
                    (student_id, selected_school_id)
                )
                if not student:
                    continue

                existing_link = fetch_one(
                    """
                    SELECT student_id
                    FROM guardians
                    WHERE student_id = ? AND parent_user_id = ?
                    """,
                    (student_id, parent_id)
                )
                if not existing_link:
                    execute_commit(
                        """
                        INSERT INTO guardians (student_id, parent_user_id)
                        VALUES (?, ?)
                        """,
                        (student_id, parent_id)
                    )
                    linked += 1

            audit(
                "Created parent",
                "users",
                parent_id,
                f"Created parent account {username}; linked {linked} student(s)"
            )

            flash("Parent account created successfully.", "success")
            return redirect(url_for("parent_profile", parent_id=parent_id))

        students_query = """
            SELECT id, first_name, last_name, student_number, class_name
            FROM students
        """
        students_params = []
        if selected_school_id:
            students_query += " WHERE school_id = ?"
            students_params.append(selected_school_id)
        elif role != "super_admin":
            students_query += " WHERE 1 = 0"
        students_query += " ORDER BY class_name, first_name, last_name"

        students = fetch_all(students_query, tuple(students_params))

        return render_template(
            "add_parent.html",
            schools=schools,
            students=students,
            selected_school_id=selected_school_id
        )

    @app.route("/parents/<int:parent_id>")
    @login_required
    @roles_required("school_admin", "super_admin")
    def parent_profile(parent_id):
        parent = get_parent_or_none(parent_id)

        if not parent:
            flash("Parent not found or access denied.", "danger")
            return redirect(url_for("parents"))

        children = fetch_all(
            """
            SELECT
                st.id,
                st.first_name,
                st.last_name,
                st.student_number,
                st.class_name
            FROM guardians g
            JOIN students st ON st.id = g.student_id
            WHERE g.parent_user_id = ?
            ORDER BY st.class_name, st.first_name, st.last_name
            """,
            (parent_id,)
        )

        available_students = fetch_all(
            """
            SELECT
                st.id,
                st.first_name,
                st.last_name,
                st.student_number,
                st.class_name
            FROM students st
            WHERE st.school_id = ?
              AND NOT EXISTS (
                    SELECT 1
                    FROM guardians g
                    WHERE g.student_id = st.id
                      AND g.parent_user_id = ?
              )
            ORDER BY st.class_name, st.first_name, st.last_name
            """,
            (parent["school_id"], parent_id)
        )

        school = fetch_one(
            "SELECT school_name FROM schools WHERE id = ?",
            (parent["school_id"],)
        )

        return render_template(
            "parent_profile.html",
            parent=parent,
            children=children,
            available_students=available_students,
            school=school
        )

    @app.route("/parents/<int:parent_id>/edit", methods=["GET", "POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def edit_parent(parent_id):
        parent = get_parent_or_none(parent_id)

        if not parent:
            flash("Parent not found or access denied.", "danger")
            return redirect(url_for("parents"))

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            username = request.form.get("username", "").strip()

            if not full_name or not username:
                flash("Full name and username are required.", "danger")
                return redirect(url_for("edit_parent", parent_id=parent_id))

            duplicate = fetch_one(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (username, parent_id)
            )
            if duplicate:
                flash("That username is already in use.", "danger")
                return redirect(url_for("edit_parent", parent_id=parent_id))

            execute_commit(
                """
                UPDATE users
                SET full_name = ?, username = ?
                WHERE id = ?
                """,
                (full_name, username, parent_id)
            )

            audit(
                "Edited parent",
                "users",
                parent_id,
                f"Updated parent account {username}"
            )

            flash("Parent details updated successfully.", "success")
            return redirect(url_for("parent_profile", parent_id=parent_id))

        return render_template("edit_parent.html", parent=parent)

    @app.route("/parents/<int:parent_id>/link-child", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def link_parent_child(parent_id):
        parent = get_parent_or_none(parent_id)

        if not parent:
            flash("Parent not found or access denied.", "danger")
            return redirect(url_for("parents"))

        student_id = request.form.get("student_id", type=int)
        student = get_student_or_none(student_id) if student_id else None

        if not student or student["school_id"] != parent["school_id"]:
            flash("The selected student is invalid.", "danger")
            return redirect(url_for("parent_profile", parent_id=parent_id))

        existing = fetch_one(
            """
            SELECT student_id
            FROM guardians
            WHERE student_id = ? AND parent_user_id = ?
            """,
            (student_id, parent_id)
        )

        if existing:
            flash("That student is already linked to this parent.", "warning")
            return redirect(url_for("parent_profile", parent_id=parent_id))

        execute_commit(
            "INSERT INTO guardians (student_id, parent_user_id) VALUES (?, ?)",
            (student_id, parent_id)
        )

        audit(
            "Linked child to parent",
            "guardians",
            student_id,
            f"Linked student {student_id} to parent {parent_id}"
        )

        flash("Student linked successfully.", "success")
        return redirect(url_for("parent_profile", parent_id=parent_id))

    @app.route(
        "/parents/<int:parent_id>/unlink-child/<int:student_id>",
        methods=["POST"]
    )
    @login_required
    @roles_required("school_admin", "super_admin")
    def unlink_parent_child(parent_id, student_id):
        parent = get_parent_or_none(parent_id)
        student = get_student_or_none(student_id)

        if not parent or not student or student["school_id"] != parent["school_id"]:
            flash("Parent or student not found.", "danger")
            return redirect(url_for("parents"))

        execute_commit(
            """
            DELETE FROM guardians
            WHERE parent_user_id = ? AND student_id = ?
            """,
            (parent_id, student_id)
        )

        audit(
            "Unlinked child from parent",
            "guardians",
            student_id,
            f"Unlinked student {student_id} from parent {parent_id}"
        )

        flash("Student link removed.", "success")
        return redirect(url_for("parent_profile", parent_id=parent_id))

    @app.route("/parents/<int:parent_id>/reset-password", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def reset_parent_password(parent_id):
        parent = get_parent_or_none(parent_id)

        if not parent:
            flash("Parent not found or access denied.", "danger")
            return redirect(url_for("parents"))

        new_password = request.form.get("new_password", "").strip()
        if not new_password:
            new_password = generate_temporary_password()

        if len(new_password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return redirect(url_for("parent_profile", parent_id=parent_id))

        execute_commit(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(new_password), parent_id)
        )

        audit(
            "Reset parent password",
            "users",
            parent_id,
            f"Reset password for parent {parent['username']}"
        )

        flash(
            f"Password reset successfully. Temporary password: {new_password}",
            "success"
        )
        return redirect(url_for("parent_profile", parent_id=parent_id))

    @app.route("/parents/<int:parent_id>/deactivate", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def deactivate_parent(parent_id):
        parent = get_parent_or_none(parent_id)

        if not parent:
            flash("Parent not found or access denied.", "danger")
            return redirect(url_for("parents"))

        execute_commit(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (0, parent_id)
        )

        audit(
            "Deactivated parent",
            "users",
            parent_id,
            f"Deactivated parent {parent['username']}"
        )

        flash("Parent account deactivated.", "success")
        return redirect(url_for("parent_profile", parent_id=parent_id))

    @app.route("/parents/<int:parent_id>/activate", methods=["POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def activate_parent(parent_id):
        parent = get_parent_or_none(parent_id)

        if not parent:
            flash("Parent not found or access denied.", "danger")
            return redirect(url_for("parents"))

        execute_commit(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1, parent_id)
        )

        audit(
            "Activated parent",
            "users",
            parent_id,
            f"Activated parent {parent['username']}"
        )

        flash("Parent account activated.", "success")
        return redirect(url_for("parent_profile", parent_id=parent_id))
