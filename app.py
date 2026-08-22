from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

from config import db, cursor

app = Flask(__name__)
app.secret_key = "dayflow-dev-secret-key-change-in-production"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "employee_id" not in session:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "Admin":
            return render_template("error.html", code=403,
                                    message="You don't have permission to access this page."), 403
        return f(*args, **kwargs)
    return wrapper


@app.before_request
def load_current_user():
    """Load the logged-in user's row into g.user so templates can use it."""
    g.user = None
    if "employee_id" in session:
        cursor.execute("SELECT * FROM users WHERE employee_id=%s", (session["employee_id"],))
        g.user = cursor.fetchone()


@app.context_processor
def inject_user():
    return {"current_user": g.get("user")}


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
@app.route("/")
def home():
    return redirect(url_for("dashboard")) if "employee_id" in session else redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm = request.form["confirm_password"]
        role = request.form.get("role", "Employee")

        if role not in ("Admin", "Employee"):
            role = "Employee"

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(url_for("signup"))

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("signup"))

        cursor.execute("SELECT employee_id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("signup"))

        hashed_pw = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (full_name, email, password, role) VALUES (%s,%s,%s,%s)",
            (name, email, hashed_pw, role)
        )
        db.commit()

        flash("Account created successfully! Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if not user or not check_password_hash(user["password"], password):
            flash("Incorrect email or password.", "danger")
            return redirect(url_for("login"))

        session["employee_id"] = user["employee_id"]
        session["role"] = user["role"]
        flash(f"Welcome back, {user['full_name']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    if session["role"] == "Admin":
        cursor.execute("SELECT * FROM users WHERE role='Employee' ORDER BY full_name")
        employees = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) AS c FROM leave_requests WHERE status='Pending'")
        pending_leaves = cursor.fetchone()["c"]

        cursor.execute("SELECT COUNT(*) AS c FROM attendance WHERE date=%s", (date.today(),))
        today_attendance = cursor.fetchone()["c"]

        return render_template("admin_dashboard.html", employees=employees,
                                pending_leaves=pending_leaves,
                                today_attendance=today_attendance,
                                total_employees=len(employees))
    else:
        cursor.execute("SELECT * FROM attendance WHERE employee_id=%s AND date=%s",
                        (session["employee_id"], date.today()))
        today_att = cursor.fetchone()

        cursor.execute("SELECT * FROM leave_requests WHERE employee_id=%s ORDER BY leave_id DESC LIMIT 5",
                        (session["employee_id"],))
        recent_leaves = cursor.fetchall()

        return render_template("employee_dashboard.html", today_att=today_att, recent_leaves=recent_leaves)


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        phone = request.form.get("phone", "")
        address = request.form.get("address", "")
        cursor.execute("UPDATE users SET phone=%s, address=%s WHERE employee_id=%s",
                        (phone, address, session["employee_id"]))
        db.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html", user=g.user)


@app.route("/admin/employee/<int:emp_id>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_employee(emp_id):
    if request.method == "POST":
        cursor.execute(
            "UPDATE users SET full_name=%s, phone=%s, address=%s WHERE employee_id=%s",
            (request.form["full_name"], request.form.get("phone", ""),
             request.form.get("address", ""), emp_id)
        )
        db.commit()
        flash("Employee profile updated.", "success")
        return redirect(url_for("admin_edit_employee", emp_id=emp_id))

    cursor.execute("SELECT * FROM users WHERE employee_id=%s", (emp_id,))
    emp = cursor.fetchone()
    if not emp:
        return render_template("error.html", code=404, message="Employee not found."), 404

    return render_template("admin_edit_employee.html", emp=emp)


# --------------------------------------------------------------------------
# Attendance
# --------------------------------------------------------------------------
@app.route("/attendance")
@login_required
def attendance():
    view = request.args.get("view", "weekly")
    start = date.today() if view == "daily" else date.today() - timedelta(days=6)

    cursor.execute(
        "SELECT * FROM attendance WHERE employee_id=%s AND date>=%s ORDER BY date DESC",
        (session["employee_id"], start)
    )
    records = cursor.fetchall()

    cursor.execute("SELECT * FROM attendance WHERE employee_id=%s AND date=%s",
                    (session["employee_id"], date.today()))
    today_att = cursor.fetchone()

    return render_template("attendance.html", records=records, view=view, today_att=today_att)


@app.route("/attendance/checkin", methods=["POST"])
@login_required
def checkin():
    emp_id = session["employee_id"]
    cursor.execute("SELECT * FROM attendance WHERE employee_id=%s AND date=%s", (emp_id, date.today()))
    today_att = cursor.fetchone()

    if today_att and today_att["check_in"]:
        flash("You have already checked in today.", "warning")
    else:
        now_time = datetime.now().time().replace(microsecond=0)
        if today_att:
            cursor.execute("UPDATE attendance SET check_in=%s, status='Present' WHERE attendance_id=%s",
                            (now_time, today_att["attendance_id"]))
        else:
            cursor.execute(
                "INSERT INTO attendance (employee_id, date, check_in, status) VALUES (%s,%s,%s,'Present')",
                (emp_id, date.today(), now_time)
            )
        db.commit()
        flash("Checked in successfully.", "success")

    return redirect(url_for("attendance"))


@app.route("/attendance/checkout", methods=["POST"])
@login_required
def checkout():
    emp_id = session["employee_id"]
    cursor.execute("SELECT * FROM attendance WHERE employee_id=%s AND date=%s", (emp_id, date.today()))
    today_att = cursor.fetchone()

    if not today_att or not today_att["check_in"]:
        flash("You need to check in before checking out.", "warning")
    elif today_att["check_out"]:
        flash("You have already checked out today.", "warning")
    else:
        now_time = datetime.now().time().replace(microsecond=0)
        cursor.execute("UPDATE attendance SET check_out=%s WHERE attendance_id=%s",
                        (now_time, today_att["attendance_id"]))
        db.commit()
        flash("Checked out successfully.", "success")

    return redirect(url_for("attendance"))


@app.route("/admin/attendance")
@login_required
@admin_required
def admin_attendance():
    selected_date_str = request.args.get("date", "")
    selected_date = date.today()
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    cursor.execute("""
        SELECT a.*, u.full_name, u.employee_id AS emp_id
        FROM attendance a
        JOIN users u ON a.employee_id = u.employee_id
        WHERE a.date=%s
        ORDER BY u.full_name
    """, (selected_date,))
    records = cursor.fetchall()

    return render_template("admin_attendance.html", records=records, selected_date=selected_date)


# --------------------------------------------------------------------------
# Leave
# --------------------------------------------------------------------------
@app.route("/leave", methods=["GET", "POST"])
@login_required
def leave():
    if request.method == "POST":
        leave_type = request.form.get("leave_type")
        start_str = request.form.get("start_date")
        end_str = request.form.get("end_date")
        remarks = request.form.get("remarks", "")

        try:
            start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            flash("Please provide a valid date range.", "danger")
            return redirect(url_for("leave"))

        if end_dt < start_dt:
            flash("End date cannot be before the start date.", "danger")
            return redirect(url_for("leave"))

        cursor.execute(
            "INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, remarks, status) "
            "VALUES (%s,%s,%s,%s,%s,'Pending')",
            (session["employee_id"], leave_type, start_dt, end_dt, remarks)
        )
        db.commit()
        flash("Leave request submitted.", "success")
        return redirect(url_for("leave"))

    cursor.execute("SELECT * FROM leave_requests WHERE employee_id=%s ORDER BY leave_id DESC",
                    (session["employee_id"],))
    my_leaves = cursor.fetchall()
    return render_template("leave.html", my_leaves=my_leaves)


@app.route("/admin/leave")
@login_required
@admin_required
def admin_leave():
    status_filter = request.args.get("status", "Pending")
    cursor.execute("""
        SELECT l.*, u.full_name
        FROM leave_requests l
        JOIN users u ON l.employee_id = u.employee_id
        WHERE l.status=%s
        ORDER BY l.leave_id DESC
    """, (status_filter,))
    all_leaves = cursor.fetchall()
    return render_template("admin_leave.html", all_leaves=all_leaves, status_filter=status_filter)


@app.route("/admin/leave/<int:leave_id>/decision", methods=["POST"])
@login_required
@admin_required
def leave_decision(leave_id):
    decision = request.form.get("decision")
    comment = request.form.get("comment", "")

    if decision not in ("Approved", "Rejected"):
        flash("Invalid decision.", "danger")
        return redirect(url_for("admin_leave"))

    cursor.execute("SELECT * FROM leave_requests WHERE leave_id=%s", (leave_id,))
    lv = cursor.fetchone()
    if not lv:
        return redirect(url_for("admin_leave"))

    cursor.execute("UPDATE leave_requests SET status=%s, admin_comment=%s WHERE leave_id=%s",
                    (decision, comment, leave_id))
    db.commit()

    if decision == "Approved":
        cur_date = lv["start_date"]
        end_date = lv["end_date"]
        while cur_date <= end_date:
            cursor.execute("SELECT * FROM attendance WHERE employee_id=%s AND date=%s",
                            (lv["employee_id"], cur_date))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("UPDATE attendance SET status='Leave' WHERE attendance_id=%s",
                                (existing["attendance_id"],))
            else:
                cursor.execute(
                    "INSERT INTO attendance (employee_id, date, status) VALUES (%s,%s,'Leave')",
                    (lv["employee_id"], cur_date)
                )
            cur_date += timedelta(days=1)
        db.commit()

    flash(f"Leave request has been {decision.lower()}.", "success")
    return redirect(url_for("admin_leave"))


# --------------------------------------------------------------------------
# Payroll
# --------------------------------------------------------------------------
def get_or_create_payroll(emp_id):
    cursor.execute("SELECT * FROM payroll WHERE employee_id=%s", (emp_id,))
    p = cursor.fetchone()
    if not p:
        cursor.execute(
            "INSERT INTO payroll (employee_id, basic_salary, bonus, total_salary) VALUES (%s,0,0,0)",
            (emp_id,)
        )
        db.commit()
        cursor.execute("SELECT * FROM payroll WHERE employee_id=%s", (emp_id,))
        p = cursor.fetchone()
    return p


@app.route("/payroll")
@login_required
def payroll():
    p = get_or_create_payroll(session["employee_id"])
    return render_template("payroll.html", payroll=p)


@app.route("/admin/payroll")
@login_required
@admin_required
def admin_payroll():
    cursor.execute("""
        SELECT u.employee_id, u.full_name,
               COALESCE(p.basic_salary,0) AS basic_salary,
               COALESCE(p.bonus,0) AS bonus,
               COALESCE(p.total_salary,0) AS total_salary
        FROM users u
        LEFT JOIN payroll p ON u.employee_id = p.employee_id
        WHERE u.role='Employee'
        ORDER BY u.full_name
    """)
    employees = cursor.fetchall()
    return render_template("admin_payroll.html", employees=employees)


@app.route("/admin/payroll/<int:emp_id>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_payroll(emp_id):
    if request.method == "POST":
        try:
            basic = float(request.form.get("basic_salary", 0) or 0)
            bonus = float(request.form.get("bonus", 0) or 0)
        except ValueError:
            flash("Salary fields must be numeric.", "danger")
            return redirect(url_for("admin_edit_payroll", emp_id=emp_id))

        total = round(basic + bonus, 2)
        get_or_create_payroll(emp_id)  # ensure a row exists
        cursor.execute(
            "UPDATE payroll SET basic_salary=%s, bonus=%s, total_salary=%s WHERE employee_id=%s",
            (basic, bonus, total, emp_id)
        )
        db.commit()
        flash("Payroll updated.", "success")
        return redirect(url_for("admin_payroll"))

    cursor.execute("SELECT * FROM users WHERE employee_id=%s", (emp_id,))
    emp = cursor.fetchone()
    p = get_or_create_payroll(emp_id)
    return render_template("admin_edit_payroll.html", emp=emp, payroll=p)


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
@app.route("/admin/reports")
@login_required
@admin_required
def admin_reports():
    cursor.execute("SELECT COUNT(*) AS c FROM users WHERE role='Employee'")
    total_employees = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM attendance WHERE date=%s AND status='Present'", (date.today(),))
    today_present = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM leave_requests WHERE status='Pending'")
    pending_leaves = cursor.fetchone()["c"]

    cursor.execute("SELECT COUNT(*) AS c FROM leave_requests WHERE status='Approved'")
    approved_leaves = cursor.fetchone()["c"]

    cursor.execute("SELECT COALESCE(SUM(total_salary),0) AS s FROM payroll")
    payroll_sum = cursor.fetchone()["s"] or 0

    # ---- Chart 1: attendance trend, last 7 days ----
    week_start = date.today() - timedelta(days=6)
    cursor.execute("""
        SELECT date, COUNT(*) AS c FROM attendance
        WHERE status='Present' AND date >= %s
        GROUP BY date
    """, (week_start,))
    trend_map = {row["date"]: row["c"] for row in cursor.fetchall()}

    trend_labels, trend_data = [], []
    for i in range(6, -1, -1):
        d = date.today() - timedelta(days=i)
        trend_labels.append(d.strftime("%a"))
        trend_data.append(trend_map.get(d, 0))

    # ---- Chart 2: leave type breakdown ----
    cursor.execute("SELECT leave_type, COUNT(*) AS c FROM leave_requests GROUP BY leave_type")
    type_rows = cursor.fetchall()
    leave_type_labels = [row["leave_type"] for row in type_rows]
    leave_type_data = [row["c"] for row in type_rows]

    # ---- Chart 3: payroll distribution (top 8 employees) ----
    cursor.execute("""
        SELECT u.full_name, COALESCE(p.total_salary,0) AS total_salary
        FROM users u
        LEFT JOIN payroll p ON u.employee_id = p.employee_id
        WHERE u.role='Employee'
        ORDER BY total_salary DESC
        LIMIT 8
    """)
    payroll_rows = cursor.fetchall()
    payroll_labels = [row["full_name"] for row in payroll_rows]
    payroll_data = [float(row["total_salary"] or 0) for row in payroll_rows]

    return render_template(
        "admin_reports.html",
        total_employees=total_employees,
        today_present=today_present,
        pending_leaves=pending_leaves,
        approved_leaves=approved_leaves,
        payroll_sum=payroll_sum,
        trend_labels=trend_labels,
        trend_data=trend_data,
        leave_type_labels=leave_type_labels,
        leave_type_data=leave_type_data,
        payroll_labels=payroll_labels,
        payroll_data=payroll_data,
    )

if __name__ == "__main__":
    app.run(debug=True)
