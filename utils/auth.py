from functools import wraps
from flask import session, flash, redirect, url_for

from utils.db import fetch_one


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


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        school_id = session.get("school_id")
        role = session.get("role")

        if role != "super_admin" and school_id:
            school = fetch_one(
                "SELECT * FROM schools WHERE id = ?",
                (school_id,)
            )

            if school:
                is_active = row_get(school, "is_active", 1)
                subscription_status = row_get(
                    school,
                    "subscription_status",
                    "active"
                )

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