from flask import render_template, request, redirect, url_for, flash, session
from datetime import datetime
import uuid
import urllib.parse
import pandas as pd

from utils.db import (
    is_postgres,
    get_db,
    convert_query,
    fetch_one,
    fetch_all,
    execute_commit
)

from utils.auth import login_required, roles_required
from utils.audit import log_audit
from utils.helpers import CLASS_OPTIONS, row_get

def generate_transaction_reference(prefix):
    now = datetime.now()
    short_id = uuid.uuid4().hex[:8].upper()

    return (
        f"{prefix}-"
        f"{now.strftime('%Y%m%d')}-"
        f"{short_id}"
    )
def cashbook_insert_income(
    cursor,
    school_id,
    payment_date,
    amount_paid,
    receipt_number,
    student_name,
    term_name,
    created_by
):

    try:
        amount = float(amount_paid or 0)
    except Exception:
        amount = 0

    if amount <= 0:
        return

    entry_date = payment_date or datetime.now().strftime("%Y-%m-%d")

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    created_by_user_id = session.get("user_id")

    transaction_reference = generate_transaction_reference("CB")

    cursor.execute(
        convert_query("""
            INSERT INTO cashbook (
                school_id,
                entry_date,
                entry_type,
                category,
                description,
                amount,
                payment_method,
                reference_number,
                created_by,
                transaction_reference,
                created_by_user_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            transaction_reference,
            created_by_user_id,
            created_at,
        ),
    )


def register_fee_routes(app):

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

        page = int(request.args.get("page", 1) or 1)
        per_page = 50
        offset = (page - 1) * per_page

        query += " ORDER BY s.class_name, s.first_name, s.last_name, f.term_name LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        fee_records = fetch_all(query, tuple(params))

        return render_template(
            "fees.html",
            fee_records=fee_records,
            search=search,
            page=page
        )

    @app.route("/add_fee", methods=["GET", "POST"])
    @login_required
    @roles_required("school_admin", "super_admin")
    def add_fee():
        school_id = session.get("school_id")
        role = session.get("role")
        user_id = session.get("user_id")

        selected_class = request.args.get("class_name", "").strip()

        # -------------------------------------------------
        # LOAD STUDENTS FOR SELECTED CLASS
        # -------------------------------------------------

        if role == "super_admin":
            students = (
                fetch_all(
                    """
                    SELECT *
                    FROM students
                    WHERE class_name = ?
                    ORDER BY first_name, last_name
                    """,
                    (selected_class,)
                )
                if selected_class
                else []
            )

        else:
            students = (
                fetch_all(
                    """
                    SELECT *
                    FROM students
                    WHERE school_id = ?
                    AND class_name = ?
                    ORDER BY first_name, last_name
                    """,
                    (school_id, selected_class)
                )
                if selected_class
                else []
            )

        # -------------------------------------------------
        # SAVE NEW FEE RECORD
        # -------------------------------------------------

        if request.method == "POST":

            student_id = request.form.get("student_id")
            term_name = request.form.get("term_name")
            due_date = request.form.get("due_date")
            payment_date = request.form.get("payment_date")

            receipt_number = request.form.get(
                "receipt_number",
                ""
            ).strip()

            try:
                amount = float(
                    request.form.get("amount") or 0
                )

                paid_amount = float(
                    request.form.get("paid_amount") or 0
                )

            except ValueError:
                flash(
                    "Amount and payment must be valid numbers.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "add_fee",
                        class_name=selected_class
                    )
                )

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------

            if not student_id or not term_name or amount <= 0:
                flash(
                    "Student, term, and total amount are required.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "add_fee",
                        class_name=selected_class
                    )
                )

            student = fetch_one(
                """
                SELECT *
                FROM students
                WHERE id = ?
                """,
                (student_id,)
            )

            if not student:
                flash(
                    "Student not found.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "add_fee",
                        class_name=selected_class
                    )
                )

            if (
                role != "super_admin"
                and row_get(student, "school_id") != school_id
            ):
                flash(
                    "Invalid student selected.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "add_fee",
                        class_name=selected_class
                    )
                )

            fee_school_id = row_get(
                student,
                "school_id",
                school_id
            )

            # -------------------------------------------------
            # CALCULATE BALANCE + STATUS
            # -------------------------------------------------

            balance = amount - paid_amount

            if balance <= 0:
                status = "Paid"
                balance = 0

            elif paid_amount > 0:
                status = "Partially Paid"

            else:
                status = "Pending"

            # -------------------------------------------------
            # COMPLIANCE METADATA
            # -------------------------------------------------

            created_by_name = (
                session.get("full_name")
                or session.get("username")
                or "System"
            )

            created_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            financial_year = str(
                datetime.now().year
            )

            # -------------------------------------------------
            # DATABASE TRANSACTION
            # -------------------------------------------------

            conn = get_db()
            cursor = conn.cursor()

            try:

                # ---------------------------------------------
                # CREATE FEE RECORD
                # ---------------------------------------------

                if is_postgres():

                    cursor.execute(
                        convert_query("""
                            INSERT INTO fees (
                                school_id,
                                student_id,
                                term_name,
                                amount,
                                paid_amount,
                                balance,
                                status,
                                due_date,
                                financial_year,
                                created_by_user_id,
                                created_by_name,
                                created_at
                            )
                            VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                            )
                            RETURNING id
                        """),
                        (
                            fee_school_id,
                            student_id,
                            term_name,
                            amount,
                            paid_amount,
                            balance,
                            status,
                            due_date,
                            financial_year,
                            user_id,
                            created_by_name,
                            created_at
                        )
                    )

                    fee_id = cursor.fetchone()["id"]

                else:

                    cursor.execute(
                        convert_query("""
                            INSERT INTO fees (
                                school_id,
                                student_id,
                                term_name,
                                amount,
                                paid_amount,
                                balance,
                                status,
                                due_date,
                                financial_year,
                                created_by_user_id,
                                created_by_name,
                                created_at
                            )
                            VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                            )
                        """),
                        (
                            fee_school_id,
                            student_id,
                            term_name,
                            amount,
                            paid_amount,
                            balance,
                            status,
                            due_date,
                            financial_year,
                            user_id,
                            created_by_name,
                            created_at
                        )
                    )

                    fee_id = cursor.lastrowid

                # ---------------------------------------------
                # INITIAL PAYMENT
                # ---------------------------------------------

                if paid_amount > 0:

                    payment_reference = (
                        generate_transaction_reference("PAY")
                    )

                    if not payment_date:
                        payment_date = datetime.now().strftime(
                            "%Y-%m-%d"
                        )

                    cursor.execute(
                        convert_query("""
                            INSERT INTO fee_payments (
                                school_id,
                                fee_id,
                                payment_date,
                                amount_paid,
                                receipt_number,
                                details,
                                transaction_reference,
                                created_by_user_id,
                                created_by_name,
                                created_at
                            )
                            VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                            )
                        """),
                        (
                            fee_school_id,
                            fee_id,
                            payment_date,
                            paid_amount,
                            receipt_number,
                            "Initial payment",
                            payment_reference,
                            user_id,
                            created_by_name,
                            created_at
                        )
                    )

                    # -----------------------------------------
                    # MATCHING CASHBOOK ENTRY
                    # -----------------------------------------

                    student_name = (
                        f"{row_get(student, 'first_name', '')} "
                        f"{row_get(student, 'last_name', '')}"
                    ).strip() or "Student"

                    cashbook_insert_income(
                        cursor,
                        fee_school_id,
                        payment_date,
                        paid_amount,
                        receipt_number,
                        student_name,
                        term_name,
                        created_by_name
                    )

                # ---------------------------------------------
                # SAVE EVERYTHING
                # ---------------------------------------------

                conn.commit()

                # ---------------------------------------------
                # AUDIT LOG
                # ---------------------------------------------

                log_audit(
                    "Added fee record",
                    "fees",
                    fee_id,
                    (
                        f"Student ID {student_id}; "
                        f"Term {term_name}; "
                        f"Amount {amount}; "
                        f"Paid {paid_amount}; "
                        f"Balance {balance}; "
                        f"Status {status}; "
                        f"Financial year {financial_year}; "
                        f"Created by {created_by_name}"
                    )
                )

                flash(
                    "Fee record added successfully.",
                    "success"
                )

                return redirect(
                    url_for("fees")
                )

            except Exception as e:

                conn.rollback()

                flash(
                    f"Error adding fee: {str(e)}",
                    "danger"
                )

                return redirect(
                    url_for(
                        "add_fee",
                        class_name=selected_class
                    )
                )

            finally:
                conn.close()

        # -------------------------------------------------
        # LOAD PAGE
        # -------------------------------------------------

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

        query = """
            SELECT
                f.*,
                s.first_name,
                s.last_name,
                s.student_number,
                s.class_name
            FROM fees f
            JOIN students s ON f.student_id = s.id
            WHERE f.id = ?
        """
        params = [fee_id]

        if role != "super_admin":
            query += " AND f.school_id = ?"
            params.append(school_id)

        fee = fetch_one(query, tuple(params))

        if not fee:
            flash("Fee record not found or access denied.", "danger")
            return redirect(url_for("fees"))

        if request.method == "POST":
            payment_date = request.form.get("payment_date", "").strip()
            receipt_number = request.form.get("receipt_number", "").strip()
            details = request.form.get("details", "").strip() or "School Fees"
            carry_forward = request.form.get("carry_forward") == "on"

            try:
                additional_payment = float(request.form.get("additional_payment") or 0)
            except Exception:
                flash("Payment amount must be a valid number.", "danger")
                return redirect(url_for("update_fee", fee_id=fee_id))

            if additional_payment <= 0:
                flash("Payment amount must be greater than zero.", "danger")
                return redirect(url_for("update_fee", fee_id=fee_id))

            if not payment_date:
                payment_date = datetime.now().strftime("%Y-%m-%d")

            old_paid_amount = float(fee["paid_amount"] or 0)
            total_amount = float(fee["amount"] or 0)

            new_paid_amount = old_paid_amount + additional_payment
            excess_amount = 0

            if new_paid_amount > total_amount:
                excess_amount = new_paid_amount - total_amount
                new_paid_amount = total_amount

            new_balance = max(total_amount - new_paid_amount, 0)

            if new_balance <= 0:
                status = "Paid"
            elif new_paid_amount > 0:
                status = "Partially Paid"
            else:
                status = "Pending"

            student_name = f"{fee['first_name']} {fee['last_name']}".strip()

            conn = get_db()
            cursor = conn.cursor()

            try:
                cursor.execute(convert_query("""
                    UPDATE fees
                    SET paid_amount = ?,
                        balance = ?,
                        status = ?
                    WHERE id = ?
                """), (
                    new_paid_amount,
                    new_balance,
                    status,
                    fee_id
                ))

                amount_for_current_fee = additional_payment - excess_amount

                if amount_for_current_fee > 0:
                    cursor.execute(convert_query("""
                        INSERT INTO fee_payments (
                            school_id,
                            fee_id,
                            payment_date,
                            amount_paid,
                            receipt_number,
                            details
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                    """), (
                        fee["school_id"],
                        fee_id,
                        payment_date,
                        amount_for_current_fee,
                        receipt_number,
                        details
                    ))

                carry_forward_message = ""

                if carry_forward and excess_amount > 0:
                    cursor.execute(convert_query("""
                        SELECT *
                        FROM fees
                        WHERE school_id = ?
                          AND student_id = ?
                          AND id != ?
                          AND balance > 0
                        ORDER BY id ASC
                        LIMIT 1
                    """), (
                        fee["school_id"],
                        fee["student_id"],
                        fee_id
                    ))

                    next_fee = cursor.fetchone()

                    if next_fee:
                        next_amount = float(next_fee["amount"] or 0)
                        next_old_paid = float(next_fee["paid_amount"] or 0)

                        next_paid = next_old_paid + excess_amount
                        remaining_excess = 0

                        if next_paid > next_amount:
                            remaining_excess = next_paid - next_amount
                            next_paid = next_amount

                        next_balance = max(next_amount - next_paid, 0)

                        if next_balance <= 0:
                            next_status = "Paid"
                        elif next_paid > 0:
                            next_status = "Partially Paid"
                        else:
                            next_status = "Pending"

                        cursor.execute(convert_query("""
                            UPDATE fees
                            SET paid_amount = ?,
                                balance = ?,
                                status = ?
                            WHERE id = ?
                        """), (
                            next_paid,
                            next_balance,
                            next_status,
                            next_fee["id"]
                        ))

                        amount_moved = excess_amount - remaining_excess

                        if amount_moved > 0:
                            cursor.execute(convert_query("""
                                INSERT INTO fee_payments (
                                    school_id,
                                    fee_id,
                                    payment_date,
                                    amount_paid,
                                    receipt_number,
                                    details
                                )
                                VALUES (?, ?, ?, ?, ?, ?)
                            """), (
                                fee["school_id"],
                                next_fee["id"],
                                payment_date,
                                amount_moved,
                                receipt_number,
                                f"Carry forward from {fee['term_name']}"
                            ))

                        carry_forward_message = f" Extra ${amount_moved:.2f} carried forward to {next_fee['term_name']}."

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
                    fee["school_id"],
                    payment_date,
                    "income",
                    "School Fees",
                    f"{details} payment from {student_name}",
                    additional_payment,
                    "School Fee Payment",
                    receipt_number,
                    session.get("full_name", "System")
                ))

                conn.commit()

                log_audit(
                    "Recorded fee payment",
                    "fees",
                    fee_id,
                    f"Added payment {additional_payment}, receipt {receipt_number}, details {details}.{carry_forward_message}"
                )

                flash(f"Payment recorded successfully.{carry_forward_message}", "success")
                return redirect(url_for("update_fee", fee_id=fee_id))

            except Exception as e:
                conn.rollback()
                flash(f"Error recording payment: {str(e)}", "danger")
                return redirect(url_for("update_fee", fee_id=fee_id))

            finally:
                conn.close()

        if role == "super_admin":
            payment_history = fetch_all("""
                SELECT *
                FROM fee_payments
                WHERE fee_id = ?
                ORDER BY payment_date DESC, id DESC
            """, (fee_id,))
        else:
            payment_history = fetch_all("""
                SELECT *
                FROM fee_payments
                WHERE fee_id = ?
                  AND school_id = ?
                ORDER BY payment_date DESC, id DESC
            """, (fee_id, school_id))

        return render_template(
            "update_fee.html",
            fee=fee,
            payment_history=payment_history,
            today=datetime.now().strftime("%Y-%m-%d")
        )

    @app.route("/fee_statement/<int:student_id>")
    @login_required
    @roles_required("school_admin", "super_admin", "parent")
    def fee_statement(student_id):
        school_id = session.get("school_id")
        role = session.get("role")
        user_id = session.get("user_id")

        if role == "parent":
            student = fetch_one("""
                SELECT s.*
                FROM students s
                JOIN guardians g ON s.id = g.student_id
                WHERE s.id = ?
                  AND g.parent_user_id = ?
                  AND s.school_id = ?
            """, (student_id, user_id, school_id))
        elif role == "super_admin":
            student = fetch_one("SELECT * FROM students WHERE id = ?", (student_id,))
        else:
            student = fetch_one("""
                SELECT * FROM students
                WHERE id = ? AND school_id = ?
            """, (student_id, school_id))

        if not student:
            flash("Student not found or access denied.", "danger")
            return redirect(url_for("fees"))

        fee_records = fetch_all("""
            SELECT *
            FROM fees
            WHERE student_id = ?
            ORDER BY term_name, due_date
        """, (student_id,))

        payments = fetch_all("""
            SELECT fp.*, f.term_name
            FROM fee_payments fp
            JOIN fees f ON fp.fee_id = f.id
            WHERE f.student_id = ?
            ORDER BY fp.payment_date DESC, fp.id DESC
        """, (student_id,))

        totals = fetch_one("""
            SELECT
                COALESCE(SUM(amount), 0) AS total_billed,
                COALESCE(SUM(paid_amount), 0) AS total_paid,
                COALESCE(SUM(balance), 0) AS total_balance
            FROM fees
            WHERE student_id = ?
        """, (student_id,))

        return render_template(
            "fee_statement.html",
            student=student,
            fee_records=fee_records,
            payments=payments,
            totals=totals,
            today=datetime.now().strftime("%Y-%m-%d")
        )

    @app.route("/fee_reminders")
    @login_required
    @roles_required("school_admin", "super_admin")
    def fee_reminders():
        school_id = session.get("school_id")
        role = session.get("role")

        query = """
            SELECT
                s.id,
                s.student_number,
                s.first_name,
                s.last_name,
                s.class_name,
                s.guardian1_name,
                s.guardian1_phone,
                COALESCE(SUM(f.balance), 0) AS total_balance
            FROM students s
            JOIN fees f ON s.id = f.student_id
            WHERE f.balance > 0
        """
        params = []

        if role != "super_admin":
            query += " AND s.school_id = ?"
            params.append(school_id)

        query += """
            GROUP BY s.id, s.student_number, s.first_name, s.last_name,
                     s.class_name, s.guardian1_name, s.guardian1_phone
            HAVING COALESCE(SUM(f.balance), 0) > 0
            ORDER BY s.class_name, s.first_name, s.last_name
        """

        students = fetch_all(query, tuple(params))

        reminder_list = []

        for student in students:
            phone = student["guardian1_phone"] or ""
            phone = phone.replace(" ", "").replace("+", "")

            message = f"""
Dear Parent/Guardian,

This is a school fee reminder for {student['first_name']} {student['last_name']}.

Outstanding balance: ${float(student['total_balance'] or 0):.2f}

Please make payment as soon as possible.

Thank you.
""".strip()

            whatsapp_link = ""
            if phone:
                whatsapp_link = "https://wa.me/" + phone + "?text=" + urllib.parse.quote(message)

            reminder_list.append({
                "student": student,
                "balance": float(student["total_balance"] or 0),
                "whatsapp_link": whatsapp_link
            })

        return render_template("fee_reminders.html", reminders=reminder_list)

    @app.route("/fee_analytics")
    @login_required
    @roles_required("school_admin", "super_admin", "director", "admin")
    def fee_analytics():
        school_id = session.get("school_id")
        role = session.get("role")

        where = ""
        params = []

        if role != "super_admin":
            where = "WHERE f.school_id = ?"
            params.append(school_id)

        summary = fetch_one(f"""
            SELECT 
                COALESCE(SUM(f.amount),0) AS total_fees,
                COALESCE(SUM(f.paid_amount),0) AS total_paid,
                COALESCE(SUM(f.balance),0) AS total_balance
            FROM fees f
            {where}
        """, tuple(params))

        status_counts = fetch_one(f"""
            SELECT 
                SUM(CASE WHEN f.status = 'Paid' THEN 1 ELSE 0 END) AS paid,
                SUM(CASE WHEN f.status = 'Partially Paid' THEN 1 ELSE 0 END) AS partial,
                SUM(CASE WHEN f.status = 'Pending' THEN 1 ELSE 0 END) AS pending
            FROM fees f
            {where}
        """, tuple(params))

        top_balances = fetch_all(f"""
            SELECT s.first_name, s.last_name, s.class_name, f.balance
            FROM fees f
            JOIN students s ON f.student_id = s.id
            {where}
            AND f.balance > 0
            ORDER BY f.balance DESC
            LIMIT 10
        """, tuple(params)) if where else fetch_all("""
            SELECT s.first_name, s.last_name, s.class_name, f.balance
            FROM fees f
            JOIN students s ON f.student_id = s.id
            WHERE f.balance > 0
            ORDER BY f.balance DESC
            LIMIT 10
        """)

        class_summary = fetch_all(f"""
            SELECT s.class_name,
                   COALESCE(SUM(f.amount),0) AS total_fees,
                   COALESCE(SUM(f.paid_amount),0) AS total_paid,
                   COALESCE(SUM(f.balance),0) AS total_balance
            FROM fees f
            JOIN students s ON f.student_id = s.id
            {where}
            GROUP BY s.class_name
            ORDER BY s.class_name
        """, tuple(params))

        return render_template(
            "fee_analytics.html",
            summary=summary,
            status_counts=status_counts,
            top_balances=top_balances,
            class_summary=class_summary
        )
    @app.route("/reports/outstanding-fees")
    @login_required
    @roles_required("school_admin", "super_admin", "director", "admin")
    def outstanding_fees_report():
        school_id = session.get("school_id")
        role = session.get("role")

        search = request.args.get("search", "").strip()
        class_name = request.args.get("class_name", "").strip()
        term_name = request.args.get("term_name", "").strip()

        page = max(int(request.args.get("page", 1) or 1), 1)
        per_page = 50
        offset = (page - 1) * per_page

        conditions = ["f.balance > 0"]
        params = []

        if role != "super_admin":
            conditions.append("f.school_id = ?")
            params.append(school_id)

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

        if class_name:
            conditions.append("s.class_name = ?")
            params.append(class_name)

        if term_name:
            conditions.append("f.term_name = ?")
            params.append(term_name)

        where_clause = " WHERE " + " AND ".join(conditions)

        report_query = f"""
            SELECT
                f.id AS fee_id,
                f.student_id,
                f.amount,
                f.paid_amount,
                f.balance,
                f.status,
                f.term_name,
                s.first_name,
                s.last_name,
                s.student_number,
                s.class_name
            FROM fees f
            JOIN students s ON f.student_id = s.id
            {where_clause}
            ORDER BY
                s.class_name,
                s.first_name,
                s.last_name,
                f.term_name
            LIMIT ? OFFSET ?
        """

        report_params = params.copy()
        report_params.extend([per_page, offset])

        outstanding_records = fetch_all(
            report_query,
            tuple(report_params)
        )

        summary = fetch_one(
            f"""
            SELECT
                COUNT(*) AS record_count,
                COUNT(DISTINCT f.student_id) AS student_count,
                COALESCE(SUM(f.amount), 0) AS total_expected,
                COALESCE(SUM(f.paid_amount), 0) AS total_paid,
                COALESCE(SUM(f.balance), 0) AS total_outstanding
            FROM fees f
            JOIN students s ON f.student_id = s.id
            {where_clause}
            """,
            tuple(params)
        )

        classes_where = []
        classes_params = []

        if role != "super_admin":
            classes_where.append("school_id = ?")
            classes_params.append(school_id)

        classes_query = """
            SELECT DISTINCT class_name
            FROM students
        """

        if classes_where:
            classes_query += " WHERE " + " AND ".join(classes_where)

        classes_query += """
            AND class_name IS NOT NULL
            AND TRIM(class_name) != ''
        """ if classes_where else """
            WHERE class_name IS NOT NULL
            AND TRIM(class_name) != ''
        """

        classes_query += " ORDER BY class_name"

        classes = fetch_all(classes_query, tuple(classes_params))

        terms_conditions = ["balance > 0"]
        terms_params = []

        if role != "super_admin":
            terms_conditions.append("school_id = ?")
            terms_params.append(school_id)

        terms = fetch_all(
            f"""
            SELECT DISTINCT term_name
            FROM fees
            WHERE {" AND ".join(terms_conditions)}
            AND term_name IS NOT NULL
            AND TRIM(term_name) != ''
            ORDER BY term_name
            """,
            tuple(terms_params)
        )
    
        return render_template(
            "reports/outstanding_fees.html",
            outstanding_records=outstanding_records,
            summary=summary,
            classes=classes,
            terms=terms,
            search=search,
            selected_class=class_name,
            selected_term=term_name,
            page=page,
            per_page=per_page
        )
    
    @app.route("/reports/payments-received")
    @login_required
    @roles_required("school_admin", "super_admin", "director", "admin")
    def payments_received_report():
        school_id = session.get("school_id")
        role = session.get("role")

        search = request.args.get("search", "").strip()
        class_name = request.args.get("class_name", "").strip()
        term_name = request.args.get("term_name", "").strip()

        conditions = ["f.paid_amount > 0"]
        params = []

        if role != "super_admin":
            conditions.append("f.school_id = ?")
            params.append(school_id)

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

        if class_name:
            conditions.append("s.class_name = ?")
            params.append(class_name)

        if term_name:
            conditions.append("f.term_name = ?")
            params.append(term_name)

        where_clause = " WHERE " + " AND ".join(conditions)

        payment_records = fetch_all(
            f"""
            SELECT
                f.id AS fee_id,
                f.student_id,
                f.amount,
                f.paid_amount,
                f.balance,
                f.status,
                f.term_name,
                s.first_name,
                s.last_name,
                s.student_number,
                s.class_name
            FROM fees f
            JOIN students s ON f.student_id = s.id
            {where_clause}
            ORDER BY
                s.class_name,
                s.first_name,
                s.last_name,
                f.term_name
            """,
            tuple(params)
        )

        summary = fetch_one(
            f"""
            SELECT
                COUNT(*) AS payment_count,
                COUNT(DISTINCT f.student_id) AS student_count,
                COALESCE(SUM(f.amount), 0) AS total_expected,
                COALESCE(SUM(f.paid_amount), 0) AS total_received,
                COALESCE(SUM(f.balance), 0) AS remaining_balance
            FROM fees f
            JOIN students s ON f.student_id = s.id
            {where_clause}
            """,
            tuple(params)
        )

        classes_conditions = [
            "class_name IS NOT NULL",
            "TRIM(class_name) != ''"
        ]
        classes_params = []

        if role != "super_admin":
            classes_conditions.append("school_id = ?")
            classes_params.append(school_id)

        classes = fetch_all(
            f"""
            SELECT DISTINCT class_name
            FROM students
            WHERE {" AND ".join(classes_conditions)}
            ORDER BY class_name
            """,
            tuple(classes_params)
        )

        terms_conditions = [
            "paid_amount > 0",
            "term_name IS NOT NULL",
            "TRIM(term_name) != ''"
        ]
        terms_params = []

        if role != "super_admin":
            terms_conditions.append("school_id = ?")
            terms_params.append(school_id)

        terms = fetch_all(
            f"""
            SELECT DISTINCT term_name
            FROM fees
            WHERE {" AND ".join(terms_conditions)}
            ORDER BY term_name
            """,
            tuple(terms_params)
        )

        return render_template(
            "reports/payments_received.html",
            payment_records=payment_records,
            summary=summary,
            classes=classes,
            terms=terms,
            search=search,
            selected_class=class_name,
            selected_term=term_name
        )

    @app.route("/print_fee_receipt/<int:payment_id>")
    @login_required
    @roles_required("school_admin", "super_admin")
    def print_fee_receipt(payment_id):
        school_id = session.get("school_id")
        role = session.get("role")

        if role == "super_admin":
            payment = fetch_one("""
                SELECT
                    fp.*,
                    f.term_name,
                    s.first_name,
                    s.last_name,
                    s.student_number,
                    s.class_name,
                    sch.school_name
                FROM fee_payments fp
                JOIN fees f ON fp.fee_id = f.id
                JOIN students s ON f.student_id = s.id
                LEFT JOIN schools sch ON f.school_id = sch.id
                WHERE fp.id = ?
            """, (payment_id,))
        else:
            payment = fetch_one("""
                SELECT
                    fp.*,
                    f.term_name,
                    s.first_name,
                    s.last_name,
                    s.student_number,
                    s.class_name,
                    sch.school_name
                FROM fee_payments fp
                JOIN fees f ON fp.fee_id = f.id
                JOIN students s ON f.student_id = s.id
                LEFT JOIN schools sch ON f.school_id = sch.id
                WHERE fp.id = ?
                  AND f.school_id = ?
            """, (payment_id, school_id))

        if not payment:
            flash("Receipt not found or access denied.", "danger")
            return redirect(url_for("fees"))

        return render_template("print_fee_receipt.html", payment=payment)