from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os

from utils.auth import login_required, roles_required
from utils.db import fetch_one, fetch_all, execute_commit
from utils.audit import log_audit
from utils.helpers import row_get, parse_date_safe, CLASS_OPTIONS


LOGO_UPLOAD_FOLDER = os.path.join("static", "uploads", "logos")
ALLOWED_LOGO_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_logo_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS


def register_admin_routes(app):

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
                execute_commit("""
                    INSERT INTO schools (school_name, school_code, is_active, subscription_status)
                    VALUES (?, ?, ?, ?)
                """, (school_name, school_code, 1, "active"))
            except Exception:
                execute_commit(
                    "INSERT INTO schools (school_name, school_code) VALUES (?, ?)",
                    (school_name, school_code)
                )

            flash("School created successfully.", "success")
            return redirect(url_for("schools"))

        return render_template("add_school.html")


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

                os.makedirs(LOGO_UPLOAD_FOLDER, exist_ok=True)
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

            execute_commit("""
                INSERT INTO users (school_id, full_name, username, password, role)
                VALUES (?, ?, ?, ?, ?)
            """, (
                school_id,
                full_name,
                username,
                generate_password_hash(password),
                "school_admin"
            ))

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

        if user["role"] == "super_admin" and current_role != "super_admin":
            flash("Only super admin can edit a super admin account.", "danger")
            return redirect(url_for("users"))

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            username = request.form.get("username", "").strip()
            new_role = request.form.get("role", "").strip()
            password = request.form.get("password", "").strip()

            if user["role"] == "super_admin" and new_role != "super_admin":
                flash("You cannot change a super admin's role.", "danger")
                return redirect(url_for("users"))

            if current_role != "super_admin" and new_role in ["super_admin", "school_admin"]:
                flash("You are not allowed to assign admin roles.", "danger")
                return redirect(url_for("users"))

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

            try:
                log_audit(
                    action="Edited user",
                    table_name="users",
                    record_id=user_id,
                    details=f"Updated {username} role to {new_role}"
                )
            except Exception:
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

        log_audit(
            "Deactivated user",
            "users",
            user_id,
            f"Deactivated {user['username']}"
        )

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

        log_audit(
            "Activated user",
            "users",
            user_id,
            f"Activated {user['username']}"
        )

        flash("User activated successfully.", "success")
        return redirect(url_for("users"))


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

            execute_commit("""
                UPDATE schools
                SET subscription_end_date = ?, subscription_status = ?, is_active = ?
                WHERE id = ?
            """, (subscription_end_date, subscription_status, is_active, school_id))

            flash("School subscription updated successfully.", "success")
            return redirect(url_for("school_profile", school_id=school_id))

        return render_template("update_school_subscription.html", school=school)


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

    @app.route("/reports")
    def reports():
        return render_template("reports.html")
    
    @app.route("/subscription_expired")
    def subscription_expired():
        school = None
        school_id = session.get("school_id")

        if school_id:
            school = fetch_one("SELECT * FROM schools WHERE id = ?", (school_id,))

        return render_template("subscription_expired.html", school=school)