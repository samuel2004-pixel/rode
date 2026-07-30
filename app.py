"""
YWAM Tailoring Training Centre - Management System
Flask app: student registration, attendance, monthly fees,
certificate generation, and CSV/PDF export.
"""
import os
import io
import csv
import calendar
from datetime import datetime, date

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_file, abort,
)

from db import get_db, init_db, get_setting, set_setting, get_user_by_username, PHOTO_DIR
from auth import login_required, admin_required, login_user, logout_user, current_user, hash_password
from certificate import generate_certificate
import biometric
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import letter, landscape, A3
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = "ywam-tailoring-centre-secret-key"


@app.context_processor
def inject_current_user():
    return {"current_user": current_user()}

COURSES = ["Basic Tailoring", "Advanced Tailoring", "Fashion Designing", "Embroidery"]
BATCHES = ["Morning", "Afternoon", "Evening"]
STATUSES = ["Active", "Completed", "Dropped"]


# ---------------------------------------------------------------- helpers
def today_str():
    return date.today().strftime("%Y-%m-%d")


def fmt_ddmmyyyy(iso_date):
    if not iso_date:
        return ""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso_date


def fee_summary(conn, student_id, monthly_fee, duration_months):
    total_due = (monthly_fee or 0) * (duration_months or 0)
    paid_row = conn.execute(
        "SELECT COALESCE(SUM(amount_paid), 0) AS total FROM fees WHERE student_id = %s",
        (student_id,),
    ).fetchone()
    total_paid = paid_row["total"]
    return total_due, total_paid, total_due - total_paid


app.jinja_env.filters["ddmmyyyy"] = fmt_ddmmyyyy


# ---------------------------------------------------------------- auth/page bootstrap
@app.before_request
def ensure_logged_in():
    # Avoid recursion while building the app is still in progress.
    try:
        login_url = url_for("login_page")
    except Exception:
        login_url = "/login"

    if request.path in (login_url, "/login"):
        return None
    if request.path.startswith("/static/"):
        return None
    if not current_user().get("is_authenticated"):
        return redirect(login_url)


# ---------------------------------------------------------------- dashboard
@app.route("/")
@login_required
def dashboard():
    conn = get_db()
    total_students = conn.execute("SELECT COUNT(*) c FROM students").fetchone()["c"]
    active_students = conn.execute(
        "SELECT COUNT(*) c FROM students WHERE status = 'Active'"
    ).fetchone()["c"]

    today = today_str()
    present_today = conn.execute(
        "SELECT COUNT(*) c FROM attendance WHERE date = %s AND status = 'Present'",
        (today,),
    ).fetchone()["c"]
    absent_today = conn.execute(
        "SELECT COUNT(*) c FROM attendance WHERE date = %s AND status = 'Absent'",
        (today,),
    ).fetchone()["c"]

    students = conn.execute("SELECT * FROM students").fetchall()
    total_due_all = 0
    total_paid_all = 0
    pending_list = []
    for s in students:
        due, paid, balance = fee_summary(conn, s["id"], s["monthly_fee"], s["duration_months"])
        total_due_all += due
        total_paid_all += paid
        if balance > 0 and s["status"] == "Active":
            pending_list.append((s, balance))
    pending_list.sort(key=lambda t: -t[1])

    recent_students = conn.execute("SELECT * FROM students ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        active_students=active_students,
        present_today=present_today,
        absent_today=absent_today,
        total_due_all=total_due_all,
        total_paid_all=total_paid_all,
        total_pending_all=total_due_all - total_paid_all,
        pending_list=pending_list[:8],
        recent_students=recent_students,
        today=today,
    )


# ---------------------------------------------------------------- exports
@app.route("/export/students.csv")
@login_required
def export_students_csv():
    conn = get_db()
    rows = conn.execute("SELECT * FROM students ORDER BY id DESC").fetchall()
    conn.close()

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["ID", "Name", "Course", "Batch", "Mobile", "Start", "End", "Status"])
    for r in rows:
        writer.writerow([r["id"], r["name"], r["course"], r["batch"],
                         r["mobile"], r["start_date"], r["end_date"], r["status"]])
    mem = io.BytesIO(si.getvalue().encode())
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name="students_report.csv")


@app.route("/export/students.pdf")
@login_required
def export_students_pdf():
    conn = get_db()
    rows = conn.execute("SELECT * FROM students ORDER BY id DESC").fetchall()
    conn.close()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter))
    story = []
    styles = getSampleStyleSheet()
    story.append(Paragraph("Students Report", styles["Title"]))
    story.append(Spacer(1, 0.2 * inch))

    data = [["ID", "Name", "Course", "Batch", "Mobile", "Start", "End", "Status"]]
    for r in rows:
        data.append([r["id"], r["name"], r["course"], r["batch"],
                     r["mobile"], r["start_date"], r["end_date"], r["status"]])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f97316")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fff7ed"), colors.white]),
    ]))
    story.append(table)
    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name="students_report.pdf")


# ---------------------------------------------------------------- students
@app.route("/students")
@login_required
def students_list():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    conn = get_db()
    sql = "SELECT * FROM students WHERE 1=1"
    params = []
    if q:
        sql += " AND (name ILIKE %s OR mobile ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    if status:
        sql += " AND status = %s"
        params.append(status)
    sql += " ORDER BY id DESC"
    students = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("students_list.html", students=students, q=q,
                            status=status, statuses=STATUSES)


@app.route("/students/add", methods=["GET", "POST"])
@login_required
def student_add():
    if request.method == "POST":
        f = request.form
        photo = request.files.get("photo")
        photo_filename = None
        if photo and photo.filename:
            ext = (photo.filename.rsplit(".", 1)[-1] or "jpg").lower()
            photo_filename = f"{secure_filename(photo.filename.rsplit('.', 1)[0])}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{__import__('random').randint(1000,9999)}.{ext}"
            photo.save(os.path.join(PHOTO_DIR, photo_filename))

        conn = get_db()
        conn.execute(
            """
            INSERT INTO students (
                name, dob, age, gender, marital_status, father_husband_name,
                mother_name, education, occupation, employment_status,
                community, religion, family_income, special_skill, prev_experience,
                course, batch, address, mobile, alt_mobile, email,
                emergency_name, emergency_relation, emergency_mobile,
                admission_date, start_date, end_date, duration_months,
                monthly_fee, status, device_user_id, photo_filename
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                f.get("name"), f.get("dob"), f.get("age") or None, f.get("gender"),
                f.get("marital_status"), f.get("father_husband_name"), f.get("mother_name"),
                f.get("education"), f.get("occupation"), f.get("employment_status"),
                f.get("community"), f.get("religion"), f.get("family_income"), f.get("special_skill"),
                f.get("prev_experience"), f.get("course"), f.get("batch"), f.get("address"),
                f.get("mobile"), f.get("alt_mobile"), f.get("email"),
                f.get("emergency_name"), f.get("emergency_relation"), f.get("emergency_mobile"),
                f.get("admission_date"), f.get("start_date"), f.get("end_date"),
                f.get("duration_months") or 3, f.get("monthly_fee") or 0,
                f.get("status") or "Active", f.get("device_user_id") or None, photo_filename,
            ),
        )
        conn.commit()
        conn.close()
        flash(f"Student '{f.get('name')}' registered successfully.", "success")
        return redirect(url_for("students_list"))

    return render_template("student_form.html", student=None, courses=COURSES,
                            batches=BATCHES, statuses=STATUSES)


@app.route("/student-photos/<path:filename>")
def student_photo(filename):
    if not filename:
        return abort(404)
    safe = os.path.basename(filename)
    path = os.path.join(PHOTO_DIR, safe)
    if not os.path.exists(path):
        return abort(404)
    try:
        return send_file(path, conditional=True)
    except Exception:
        return abort(404)


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@login_required
def student_edit(sid):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = %s", (sid,)).fetchone()
    if not student:
        conn.close()
        abort(404)

    if request.method == "POST":
        f = request.form
        photo = request.files.get("photo")
        photo_filename = student["photo_filename"]
        old_photo = photo_filename
        if f.get("remove_photo") and old_photo:
            photo_filename = None
        if photo and photo.filename:
            ext = (photo.filename.rsplit(".", 1)[-1] or "jpg").lower()
            photo_filename = f"{secure_filename(photo.filename.rsplit('.', 1)[0])}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{__import__('random').randint(1000,9999)}.{ext}"
            photo.save(os.path.join(PHOTO_DIR, photo_filename))
        if old_photo and old_photo != photo_filename:
            try:
                os.remove(os.path.join(PHOTO_DIR, old_photo))
            except FileNotFoundError:
                pass
        conn.execute(
            """
            UPDATE students SET
                name=%s, dob=%s, age=%s, gender=%s, marital_status=%s,
                father_husband_name=%s, mother_name=%s, education=%s,
                occupation=%s, employment_status=%s, community=%s, religion=%s,
                family_income=%s, special_skill=%s, prev_experience=%s,
                course=%s, batch=%s, address=%s, mobile=%s, alt_mobile=%s, email=%s,
                emergency_name=%s, emergency_relation=%s, emergency_mobile=%s,
                admission_date=%s, start_date=%s, end_date=%s, duration_months=%s,
                monthly_fee=%s, status=%s, device_user_id=%s, photo_filename=%s
            WHERE id=%s
            """,
            (
                f.get("name"), f.get("dob"), f.get("age") or None, f.get("gender"),
                f.get("marital_status"), f.get("father_husband_name"), f.get("mother_name"),
                f.get("education"), f.get("occupation"), f.get("employment_status"),
                f.get("community"), f.get("religion"), f.get("family_income"), f.get("special_skill"),
                f.get("prev_experience"), f.get("course"), f.get("batch"), f.get("address"),
                f.get("mobile"), f.get("alt_mobile"), f.get("email"),
                f.get("emergency_name"), f.get("emergency_relation"), f.get("emergency_mobile"),
                f.get("admission_date"), f.get("start_date"), f.get("end_date"),
                f.get("duration_months") or 3, f.get("monthly_fee") or 0,
                f.get("status") or "Active", f.get("device_user_id") or None, photo_filename, sid,
            ),
        )
        conn.commit()
        conn.close()
        flash("Student details updated.", "success")
        return redirect(url_for("student_view", sid=sid))

    conn.close()
    return render_template("student_form.html", student=student, courses=COURSES,
                            batches=BATCHES, statuses=STATUSES)


@app.route("/students/<int:sid>")
@login_required
def student_view(sid):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = %s", (sid,)).fetchone()
    if not student:
        conn.close()
        abort(404)
    attendance = conn.execute(
        "SELECT * FROM attendance WHERE student_id = %s ORDER BY date DESC",
        (sid,),
    ).fetchall()
    present_count = sum(1 for a in attendance if a["status"] == "Present")
    absent_count = sum(1 for a in attendance if a["status"] == "Absent")

    fees = conn.execute(
        "SELECT * FROM fees WHERE student_id = %s ORDER BY month DESC",
        (sid,),
    ).fetchall()
    due, paid, balance = fee_summary(conn, sid, student["monthly_fee"], student["duration_months"])

    certs = conn.execute(
        "SELECT * FROM certificates WHERE student_id = %s ORDER BY id DESC",
        (sid,),
    ).fetchall()
    conn.close()

    return render_template(
        "student_view.html", student=student, attendance=attendance,
        present_count=present_count, absent_count=absent_count,
        fees=fees, due=due, paid=paid, balance=balance, certs=certs,
    )


@app.route("/students/<int:sid>/delete", methods=["POST"])
@login_required
def student_delete(sid):
    conn = get_db()
    conn.execute("DELETE FROM students WHERE id = %s", (sid,))
    conn.commit()
    conn.close()
    flash("Student record deleted.", "info")
    return redirect(url_for("students_list"))


# ---------------------------------------------------------------- attendance
@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance_page():
    today = date.today()

    def _parse_my(source):
        try:
            mon = int(source.get("month") or today.month)
            year = int(source.get("year") or today.year)
            date(year, mon, 1)
        except (ValueError, TypeError):
            mon, year = today.month, today.year
        return year, mon

    if request.method == "POST":
        year, mon = _parse_my(request.form)
        days_in_month = calendar.monthrange(year, mon)[1]

        conn = get_db()
        students = conn.execute("SELECT id FROM students WHERE status = 'Active'").fetchall()
        changed = 0
        for s in students:
            sid = s["id"]
            for d in range(1, days_in_month + 1):
                if request.form.get(f"touched_{sid}_{d}") != "1":
                    continue  # cell wasn't clicked - leave any existing record untouched
                val = request.form.get(f"mark_{sid}_{d}", "")
                date_str = f"{year:04d}-{mon:02d}-{d:02d}"
                changed += 1
                if val in ("Present", "Absent"):
                    conn.execute(
                        """
                        INSERT INTO attendance (student_id, date, status, source)
                        VALUES (%s, %s, %s, 'Manual')
                        ON CONFLICT (student_id, date) DO UPDATE SET status=EXCLUDED.status, source='Manual'
                        """,
                        (sid, date_str, val),
                    )
                else:
                    conn.execute(
                        "DELETE FROM attendance WHERE student_id = %s AND date = %s",
                        (sid, date_str),
                    )
        conn.commit()
        conn.close()
        if changed:
            flash(f"Attendance saved for {calendar.month_name[mon]} {year} ({changed} change(s)).", "success")
        else:
            flash("No changes to save.", "info")
        return redirect(url_for("attendance_page", month=mon, year=year))

    year, mon = _parse_my(request.args)
    days_in_month = calendar.monthrange(year, mon)[1]
    start_date = f"{year:04d}-{mon:02d}-01"
    end_date = f"{year:04d}-{mon:02d}-{days_in_month:02d}"

    conn = get_db()
    students = conn.execute(
        "SELECT * FROM students WHERE status = 'Active' ORDER BY name"
    ).fetchall()
    marks = {}
    sources = {}
    totals = {s["id"]: {"worked": 0, "leave": 0} for s in students}
    for row in conn.execute(
        "SELECT student_id, date, status, source FROM attendance WHERE date >= %s AND date <= %s",
        (start_date, end_date),
    ):
        day_num = int(row["date"].split("-")[2])
        marks[(row["student_id"], day_num)] = row["status"]
        sources[(row["student_id"], day_num)] = row["source"]
        if row["student_id"] in totals:
            if row["status"] == "Present":
                totals[row["student_id"]]["worked"] += 1
            elif row["status"] == "Absent":
                totals[row["student_id"]]["leave"] += 1
    conn.close()

    today_day = today.day if (today.year == year and today.month == mon) else None
    prev_mon, prev_year = (12, year - 1) if mon == 1 else (mon - 1, year)
    next_mon, next_year = (1, year + 1) if mon == 12 else (mon + 1, year)

    return render_template(
        "attendance.html", students=students, marks=marks, sources=sources, totals=totals,
        month=mon, year=year, days_in_month=days_in_month,
        month_label=f"{calendar.month_name[mon]} {year}",
        month_names=[calendar.month_name[m] for m in range(1, 13)],
        today_day=today_day,
        prev_mon=prev_mon, prev_year=prev_year,
        next_mon=next_mon, next_year=next_year,
        sync_date=today_str() if (today.year == year and today.month == mon) else start_date,
    )


@app.route("/attendance/history")
@login_required
def attendance_history():
    student_id = request.args.get("student_id", "")
    start = request.args.get("start", "")
    end = request.args.get("end", "")

    conn = get_db()
    sql = """
        SELECT a.*, s.name AS student_name FROM attendance a
        JOIN students s ON s.id = a.student_id WHERE 1=1
    """
    params = []
    if student_id:
        sql += " AND a.student_id = %s"
        params.append(student_id)
    if start:
        sql += " AND a.date >= %s"
        params.append(start)
    if end:
        sql += " AND a.date <= %s"
        params.append(end)
    sql += " ORDER BY a.date DESC, s.name"
    records = conn.execute(sql, params).fetchall()
    students = conn.execute("SELECT id, name FROM students ORDER BY name").fetchall()
    conn.close()

    today = date.today()
    return render_template("attendance_history.html", records=records,
                            students=students, student_id=student_id,
                            start=start, end=end,
                            month_names=[calendar.month_name[m] for m in range(1, 13)],
                            now_month=today.month, now_year=today.year)


# ---------------------------------------------------------------- staff attendance
@app.route("/staff-attendance", methods=["GET", "POST"])
@login_required
def staff_attendance_page():
    today = date.today()

    def _parse_my(source):
        try:
            mon = int(source.get("month") or today.month)
            year = int(source.get("year") or today.year)
            date(year, mon, 1)
        except (ValueError, TypeError):
            mon, year = today.month, today.year
        return year, mon

    if request.method == "POST":
        year, mon = _parse_my(request.form)
        days_in_month = calendar.monthrange(year, mon)[1]

        conn = get_db()
        staff = conn.execute("SELECT id FROM users WHERE is_active = 1").fetchall()
        changed = 0
        for u in staff:
            uid = u["id"]
            for d in range(1, days_in_month + 1):
                if request.form.get(f"touched_{uid}_{d}") != "1":
                    continue  # cell wasn't clicked - leave any existing record untouched
                val = request.form.get(f"mark_{uid}_{d}", "")
                date_str = f"{year:04d}-{mon:02d}-{d:02d}"
                changed += 1
                if val in ("Present", "Absent"):
                    conn.execute(
                        """
                        INSERT INTO staff_attendance (staff_id, date, status)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (staff_id, date) DO UPDATE SET status=EXCLUDED.status
                        """,
                        (uid, date_str, val),
                    )
                else:
                    conn.execute(
                        "DELETE FROM staff_attendance WHERE staff_id = %s AND date = %s",
                        (uid, date_str),
                    )
        conn.commit()
        conn.close()
        if changed:
            flash(f"Staff attendance saved for {calendar.month_name[mon]} {year} ({changed} change(s)).", "success")
        else:
            flash("No changes to save.", "info")
        return redirect(url_for("staff_attendance_page", month=mon, year=year))

    year, mon = _parse_my(request.args)
    days_in_month = calendar.monthrange(year, mon)[1]
    start_date = f"{year:04d}-{mon:02d}-01"
    end_date = f"{year:04d}-{mon:02d}-{days_in_month:02d}"

    conn = get_db()
    staff = conn.execute(
        "SELECT * FROM users WHERE is_active = 1 ORDER BY full_name, username"
    ).fetchall()
    marks = {}
    totals = {u["id"]: {"worked": 0, "leave": 0} for u in staff}
    for row in conn.execute(
        "SELECT staff_id, date, status FROM staff_attendance WHERE date >= %s AND date <= %s",
        (start_date, end_date),
    ):
        day_num = int(row["date"].split("-")[2])
        marks[(row["staff_id"], day_num)] = row["status"]
        if row["staff_id"] in totals:
            if row["status"] == "Present":
                totals[row["staff_id"]]["worked"] += 1
            elif row["status"] == "Absent":
                totals[row["staff_id"]]["leave"] += 1
    conn.close()

    today_day = today.day if (today.year == year and today.month == mon) else None
    prev_mon, prev_year = (12, year - 1) if mon == 1 else (mon - 1, year)
    next_mon, next_year = (1, year + 1) if mon == 12 else (mon + 1, year)

    return render_template(
        "staff_attendance.html", staff=staff, marks=marks, totals=totals,
        month=mon, year=year, days_in_month=days_in_month,
        month_label=f"{calendar.month_name[mon]} {year}",
        month_names=[calendar.month_name[m] for m in range(1, 13)],
        today_day=today_day,
        prev_mon=prev_mon, prev_year=prev_year,
        next_mon=next_mon, next_year=next_year,
    )


@app.route("/staff-attendance/history")
@login_required
def staff_attendance_history():
    staff_id = request.args.get("staff_id", "")
    start = request.args.get("start", "")
    end = request.args.get("end", "")

    conn = get_db()
    sql = """
        SELECT a.*, u.full_name, u.username FROM staff_attendance a
        JOIN users u ON u.id = a.staff_id WHERE 1=1
    """
    params = []
    if staff_id:
        sql += " AND a.staff_id = %s"
        params.append(staff_id)
    if start:
        sql += " AND a.date >= %s"
        params.append(start)
    if end:
        sql += " AND a.date <= %s"
        params.append(end)
    sql += " ORDER BY a.date DESC, u.full_name"
    records = conn.execute(sql, params).fetchall()
    staff = conn.execute("SELECT id, full_name, username FROM users ORDER BY full_name, username").fetchall()
    conn.close()

    return render_template("staff_attendance_history.html", records=records,
                            staff=staff, staff_id=staff_id, start=start, end=end)


# ---------------------------------------------------------------- biometric device
@app.route("/settings/device", methods=["GET", "POST"])
@login_required
def device_settings():
    conn = get_db()
    if request.method == "POST":
        set_setting(conn, "device_ip", request.form.get("device_ip", "").strip())
        set_setting(conn, "device_port", request.form.get("device_port", "4370").strip() or "4370")
        set_setting(conn, "device_password", request.form.get("device_password", "0").strip() or "0")
        flash("Device settings saved.", "success")
        return redirect(url_for("device_settings"))

    device_ip = get_setting(conn, "device_ip", "")
    device_port = get_setting(conn, "device_port", "4370")
    device_password = get_setting(conn, "device_password", "0")
    conn.close()
    return render_template("device_settings.html", device_ip=device_ip,
                            device_port=device_port, device_password=device_password)


@app.route("/settings/device/test", methods=["POST"])
@login_required
def device_test():
    ip = request.form.get("device_ip", "").strip()
    port = request.form.get("device_port", "4370").strip() or "4370"
    password = request.form.get("device_password", "0").strip() or "0"
    try:
        info = biometric.test_connection(ip, port, password)
        flash(
            f"Connected successfully. Device: {info.get('device_name', 'ZKTeco')} | "
            f"Firmware: {info.get('firmware_version')} | "
            f"Enrolled users: {info.get('user_count')}",
            "success",
        )
    except biometric.BiometricError as e:
        flash(str(e), "danger")
    return redirect(url_for("device_settings"))


@app.route("/students/device-users")
@login_required
def device_users_list():
    """Shows users enrolled on the biometric device, to help map them to students."""
    conn = get_db()
    device_ip = get_setting(conn, "device_ip", "")
    device_port = get_setting(conn, "device_port", "4370")
    device_password = get_setting(conn, "device_password", "0")

    device_users = []
    error = None
    if device_ip:
        try:
            device_users = biometric.fetch_device_users(device_ip, device_port, device_password)
        except biometric.BiometricError as e:
            error = str(e)
    else:
        error = "No device IP configured yet."

    mapped = {r["device_user_id"]: r["name"] for r in conn.execute(
        "SELECT device_user_id, name FROM students WHERE device_user_id IS NOT NULL AND device_user_id != ''")}
    students = conn.execute("SELECT id, name, device_user_id FROM students ORDER BY name").fetchall()
    conn.close()

    return render_template("device_users.html", device_users=device_users, error=error,
                            mapped=mapped, students=students, device_ip=device_ip)


@app.route("/students/device-users/save", methods=["POST"])
@login_required
def save_device_links():
    conn = get_db()
    students = conn.execute("SELECT id FROM students").fetchall()
    for s in students:
        key = f"device_id_{s['id']}"
        if key in request.form:
            val = request.form.get(key, "").strip() or None
            conn.execute("UPDATE students SET device_user_id = %s WHERE id = %s", (val, s["id"]))
    conn.commit()
    conn.close()
    flash("Biometric ID links saved.", "success")
    return redirect(url_for("device_users_list"))


@app.route("/attendance/sync", methods=["POST"])
@login_required
def attendance_sync():
    sel_date = request.form.get("date") or today_str()
    sel_dt = datetime.strptime(sel_date, "%Y-%m-%d").date()
    redirect_kwargs = {"month": sel_dt.month, "year": sel_dt.year}

    conn = get_db()
    device_ip = get_setting(conn, "device_ip", "")
    device_port = get_setting(conn, "device_port", "4370")
    device_password = get_setting(conn, "device_password", "0")

    if not device_ip:
        conn.close()
        flash("No biometric device configured yet. Go to Settings → Biometric Device first.", "danger")
        return redirect(url_for("attendance_page", **redirect_kwargs))

    target_date = sel_dt
    try:
        logs = biometric.fetch_attendance_for_date(device_ip, target_date, device_port, device_password)
    except biometric.BiometricError as e:
        conn.close()
        flash(str(e), "danger")
        return redirect(url_for("attendance_page", **redirect_kwargs))

    students = conn.execute(
        "SELECT id, name, device_user_id FROM students WHERE status='Active'"
    ).fetchall()
    by_device_id = {s["device_user_id"]: s for s in students if s["device_user_id"]}

    punched_ids = set()
    unmatched_device_ids = set()
    for log in logs:
        did = log["device_user_id"]
        if did in by_device_id:
            punched_ids.add(by_device_id[did]["id"])
        else:
            unmatched_device_ids.add(did)

    for sid in punched_ids:
        conn.execute(
            """
            INSERT INTO attendance (student_id, date, status, source)
            VALUES (%s, %s, 'Present', 'Biometric')
            ON CONFLICT (student_id, date) DO UPDATE SET status='Present', source='Biometric'
            """,
            (sid, sel_date),
        )
    conn.commit()
    conn.close()

    no_punch = len(students) - len(punched_ids)
    msg = f"Synced {sel_date}: {len(punched_ids)} student(s) marked Present from device punches."
    if no_punch > 0:
        msg += f" {no_punch} active student(s) had no punch — review and mark manually below."
    if unmatched_device_ids:
        msg += (f" {len(unmatched_device_ids)} device fingerprint ID(s) punched but aren't "
                f"linked to any student yet (Students → Link Biometric IDs).")
    flash(msg, "success" if punched_ids else "info")
    return redirect(url_for("attendance_page", **redirect_kwargs))


# ---------------------------------------------------------------- fees
@app.route("/fees", methods=["GET", "POST"])
@login_required
def fees_page():
    conn = get_db()
    if request.method == "POST":
        f = request.form
        conn.execute(
            """
            INSERT INTO fees (student_id, month, amount_paid, payment_date, mode, remarks)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                f.get("student_id"), f.get("month"), f.get("amount_paid") or 0,
                f.get("payment_date"), f.get("mode"), f.get("remarks"),
            ),
        )
        conn.commit()
        flash("Fee payment recorded.", "success")
        return redirect(url_for("fees_page"))

    students = conn.execute("SELECT id, name FROM students ORDER BY name").fetchall()
    fees = conn.execute(
        """
        SELECT f.*, s.name AS student_name FROM fees f
        JOIN students s ON s.id = f.student_id ORDER BY f.payment_date DESC, f.id DESC
        """
    ).fetchall()
    conn.close()

    recent = []
    for f in fees[:10]:
        recent.append({
            "id": f["id"],
            "student_name": f["student_name"],
            "month": f["month"],
            "amount_paid": f["amount_paid"],
            "payment_date": f["payment_date"],
            "mode": f["mode"],
        })

    return render_template("fees.html", students=students, fees=recent)


@app.route("/fees/history")
@login_required
def fees_history():
    student_id = request.args.get("student_id", "")
    month = request.args.get("month", "")
    start = request.args.get("start", "")
    end = request.args.get("end", "")

    conn = get_db()
    sql = """
        SELECT f.*, s.name AS student_name, s.course FROM fees f
        JOIN students s ON s.id = f.student_id WHERE 1=1
    """
    params = []
    if student_id:
        sql += " AND f.student_id = %s"
        params.append(student_id)
    if month:
        sql += " AND f.month = %s"
        params.append(month)
    if start:
        sql += " AND f.payment_date >= %s"
        params.append(start)
    if end:
        sql += " AND f.payment_date <= %s"
        params.append(end)
    sql += " ORDER BY f.payment_date DESC, f.id DESC"
    records = conn.execute(sql, params).fetchall()
    students = conn.execute("SELECT id, name FROM students ORDER BY name").fetchall()
    total = sum((r["amount_paid"] or 0) for r in records)
    conn.close()

    return render_template("fees_history.html", records=records, students=students,
                            student_id=student_id, month=month, start=start, end=end, total=total)


@app.route("/fees/<int:fid>/delete", methods=["POST"])
@login_required
def fee_delete(fid):
    conn = get_db()
    conn.execute("DELETE FROM fees WHERE id = %s", (fid,))
    conn.commit()
    conn.close()
    flash("Fee record deleted.", "info")
    return redirect(url_for("fees_page"))


def _parse_month_year():
    """Read 'month' (1-12) and 'year' (e.g. 2026) query params and return
    (year, mon), defaulting to the current month/year on anything invalid."""
    today = date.today()
    try:
        mon = int(request.args.get("month") or today.month)
        year = int(request.args.get("year") or today.year)
        date(year, mon, 1)
    except (ValueError, TypeError):
        year, mon = today.year, today.month
    return year, mon


def _attendance_register_data(year, mon, student_id):
    """Fetch students + their day-by-day marks for one month, laid out like
    the centre's paper ' Attendance' register: Sl.No / Name /
    Designation / Working Hours / 1..31 / No. of days worked /
    No. of days leave / Remarks."""
    days_in_month = calendar.monthrange(year, mon)[1]
    start_date = f"{year:04d}-{mon:02d}-01"
    end_date = f"{year:04d}-{mon:02d}-{days_in_month:02d}"

    conn = get_db()
    stu_sql = "SELECT id, name, course, batch FROM students WHERE 1=1"
    stu_params = []
    if student_id:
        stu_sql += " AND id = %s"
        stu_params.append(student_id)
    stu_sql += " ORDER BY name"
    students = conn.execute(stu_sql, stu_params).fetchall()

    att_sql = "SELECT student_id, date, status FROM attendance WHERE date >= %s AND date <= %s"
    att_params = [start_date, end_date]
    if student_id:
        att_sql += " AND student_id = %s"
        att_params.append(student_id)
    att_rows = conn.execute(att_sql, att_params).fetchall()
    conn.close()

    marks = {}
    for r in att_rows:
        day_num = int(r["date"].split("-")[2])
        marks[(r["student_id"], day_num)] = r["status"]

    return students, marks, days_in_month


@app.route("/export/attendance/csv")
@login_required
def export_attendance_csv():
    year, mon = _parse_month_year()
    student_id = request.args.get("student_id", "")
    students, marks, days_in_month = _attendance_register_data(year, mon, student_id)
    month_label = date(year, mon, 1).strftime("%B %Y")

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow([f" Attendance for the Month of {month_label}"])
    writer.writerow([])
    header = ["Sl.No", "Name", "Designation", "Working Hours"] + \
        [str(d) for d in range(1, days_in_month + 1)] + \
        ["No. of days worked", "No. of days leave", "Remarks"]
    writer.writerow(header)

    for idx, s in enumerate(students, start=1):
        row = [idx, s["name"], s["course"] or "", s["batch"] or ""]
        worked = leave = 0
        for d in range(1, days_in_month + 1):
            st = marks.get((s["id"], d))
            if st == "Present":
                row.append("P")
                worked += 1
            elif st == "Absent":
                row.append("A")
                leave += 1
            else:
                row.append("")
        row += [worked, leave, ""]
        writer.writerow(row)

    if not students:
        writer.writerow(["-", "No students found", "", ""] + [""] * days_in_month + ["", "", ""])

    mem = io.BytesIO(si.getvalue().encode())
    fname = f"attendance_register_{year:04d}-{mon:02d}.csv"
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name=fname)


@app.route("/export/attendance/pdf")
@login_required
def export_attendance_pdf():
    """Monthly attendance register PDF: one row per student, one column per
    day of the month, laid out like the centre's paper ' Attendance'
    register (Sl.No / Name / Designation / Working Hours / 1..31 /
    No. of days worked / No. of days leave / Remarks)."""
    year, mon = _parse_month_year()
    student_id = request.args.get("student_id", "")
    students, marks, days_in_month = _attendance_register_data(year, mon, student_id)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A3),
                             topMargin=22, bottomMargin=22, leftMargin=18, rightMargin=18)
    styles = getSampleStyleSheet()
    story = []
    month_label = date(year, mon, 1).strftime("%B %Y")
    story.append(Paragraph("YWAM Tailoring Training Centre", styles["Title"]))
    story.append(Paragraph(f" Attendance for the Month of {month_label}", styles["Heading2"]))
    story.append(Spacer(1, 0.15 * inch))

    header = ["Sl.No", "Name", "Designation", "Working\nHours"] + \
        [str(d) for d in range(1, days_in_month + 1)] + \
        ["No. of\ndays\nworked", "No. of\ndays\nleave", "Remarks"]
    data = [header]
    for idx, s in enumerate(students, start=1):
        row = [str(idx), s["name"], s["course"] or "", s["batch"] or ""]
        worked = leave = 0
        for d in range(1, days_in_month + 1):
            st = marks.get((s["id"], d))
            if st == "Present":
                row.append("P")
                worked += 1
            elif st == "Absent":
                row.append("A")
                leave += 1
            else:
                row.append("")
        row.append(str(worked))
        row.append(str(leave))
        row.append("")
        data.append(row)

    if not students:
        data.append(["-", "No students found", "", ""] + [""] * days_in_month + ["", "", ""])

    day_col_w = 0.24 * inch
    col_widths = [0.35 * inch, 1.5 * inch, 0.9 * inch, 0.6 * inch] + [day_col_w] * days_in_month + \
        [0.55 * inch, 0.5 * inch, 0.9 * inch]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4b8c1")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#7a1f3d")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f3e6")]),
    ]
    for r_idx, s in enumerate(students, start=1):
        for d in range(1, days_in_month + 1):
            st = marks.get((s["id"], d))
            col = 4 + (d - 1)
            if st == "Present":
                style_cmds.append(("TEXTCOLOR", (col, r_idx), (col, r_idx), colors.HexColor("#2e7d32")))
                style_cmds.append(("FONTNAME", (col, r_idx), (col, r_idx), "Helvetica-Bold"))
            elif st == "Absent":
                style_cmds.append(("TEXTCOLOR", (col, r_idx), (col, r_idx), colors.HexColor("#c62828")))
                style_cmds.append(("FONTNAME", (col, r_idx), (col, r_idx), "Helvetica-Bold"))
    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    story.append(Spacer(1, 0.18 * inch))
    story.append(Paragraph("P = Present &nbsp;&nbsp;&nbsp; A = Absent &nbsp;&nbsp;&nbsp; Blank = No record", styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    fname = f"attendance_register_{year:04d}-{mon:02d}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=fname)


@app.route("/export/fees/csv")
@login_required
def export_fees_csv():
    student_id = request.args.get("student_id", "")
    month = request.args.get("month", "")
    start = request.args.get("start", "")
    end = request.args.get("end", "")

    conn = get_db()
    sql = """
        SELECT f.payment_date, s.name AS student_name, s.course, s.batch,
               f.month, f.amount_paid, f.mode, f.remarks
        FROM fees f
        JOIN students s ON s.id = f.student_id WHERE 1=1
    """
    params = []
    if student_id:
        sql += " AND f.student_id = %s"
        params.append(student_id)
    if month:
        sql += " AND f.month = %s"
        params.append(month)
    if start:
        sql += " AND f.payment_date >= %s"
        params.append(start)
    if end:
        sql += " AND f.payment_date <= %s"
        params.append(end)
    sql += " ORDER BY f.payment_date DESC, f.id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["Date", "Student", "Course", "Batch", "Month", "Amount", "Mode", "Remarks"])
    for r in rows:
        writer.writerow([r["payment_date"], r["student_name"], r["course"], r["batch"],
                         r["month"], "%.2f" % (r["amount_paid"] or 0), r["mode"], r["remarks"]])
    mem = io.BytesIO(si.getvalue().encode())
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name="fee_report.csv")


@app.route("/export/fees/pdf")
@login_required
def export_fees_pdf():
    student_id = request.args.get("student_id", "")
    month = request.args.get("month", "")
    start = request.args.get("start", "")
    end = request.args.get("end", "")

    conn = get_db()
    sql = """
        SELECT f.payment_date, s.name AS student_name, s.course, s.batch,
               f.month, f.amount_paid, f.mode, f.remarks
        FROM fees f
        JOIN students s ON s.id = f.student_id WHERE 1=1
    """
    params = []
    if student_id:
        sql += " AND f.student_id = %s"
        params.append(student_id)
    if month:
        sql += " AND f.month = %s"
        params.append(month)
    if start:
        sql += " AND f.payment_date >= %s"
        params.append(start)
    if end:
        sql += " AND f.payment_date <= %s"
        params.append(end)
    sql += " ORDER BY f.payment_date DESC, f.id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter))
    story = []
    styles = getSampleStyleSheet()
    story.append(Paragraph("Fee Payments Report", styles["Title"]))
    story.append(Spacer(1, 0.2 * inch))

    data = [["Date", "Student", "Course", "Batch", "Month", "Amount", "Mode", "Remarks"]]
    for r in rows:
        data.append([r["payment_date"], r["student_name"], r["course"], r["batch"],
                     r["month"], "%.2f" % (r["amount_paid"] or 0), r["mode"], r["remarks"]])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f97316")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fff7ed"), colors.white]),
    ]))
    story.append(table)
    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name="fee_report.pdf")


# ---------------------------------------------------------------- certificates
@app.route("/certificate/<int:sid>")
@login_required
def certificate_page(sid):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = %s", (sid,)).fetchone()
    if not student:
        conn.close()
        abort(404)
    conn.close()
    return render_template("certificate_form.html", student=student)


@app.route("/certificate/<int:sid>/issue", methods=["POST"])
@login_required
def issue_certificate(sid):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = %s", (sid,)).fetchone()
    if not student:
        conn.close()
        abort(404)
    name = (request.form.get("name") or student["name"] or "").strip()
    duration_months = int(request.form.get("duration_months") or student["duration_months"] or 3)
    start_date = request.form.get("start_date") or student["start_date"]
    end_date = request.form.get("end_date") or student["end_date"]

    try:
        pdf_bytes = generate_certificate(name, duration_months, fmt_ddmmyyyy(start_date), fmt_ddmmyyyy(end_date))
    except Exception as e:
        conn.close()
        app.logger.exception("Certificate generation failed for student %s", sid)
        flash(f"Could not generate the certificate: {e}", "danger")
        return redirect(url_for("certificate_page", sid=sid))

    conn.execute(
        """
        INSERT INTO certificates (student_id, duration_months, start_date, end_date)
        VALUES (%s, %s, %s, %s)
        """,
        (sid, duration_months, start_date, end_date),
    )
    conn.commit()
    conn.close()

    safe_name = secure_filename(name) or f"student_{sid}"
    fname = f"{safe_name}_certificate.pdf"
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True,
                     download_name=fname)


@app.route("/certificate/<int:sid>/<int:cert_id>/download")
@login_required
def download_certificate(sid, cert_id):
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id = %s", (sid,)).fetchone()
    cert = conn.execute(
        "SELECT * FROM certificates WHERE id = %s AND student_id = %s", (cert_id, sid)
    ).fetchone()
    conn.close()
    if not student or not cert:
        abort(404)

    try:
        pdf_bytes = generate_certificate(
            student["name"], cert["duration_months"],
            fmt_ddmmyyyy(cert["start_date"]), fmt_ddmmyyyy(cert["end_date"]),
        )
    except Exception as e:
        app.logger.exception("Certificate re-download failed for student %s / cert %s", sid, cert_id)
        flash(f"Could not generate the certificate: {e}", "danger")
        return redirect(url_for("student_view", sid=sid))

    safe_name = secure_filename(student["name"]) or f"student_{sid}"
    fname = f"{safe_name}_certificate.pdf"
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True,
                     download_name=fname)


# ---------------------------------------------------------------- settings/users
@app.route("/users", methods=["GET", "POST"])
@admin_required
def users_page():
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template("users.html", users=users)


@app.route("/users/create", methods=["POST"])
@admin_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", "Staff")
    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("users_page"))

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (%s,%s,%s,%s)",
            (username, hash_password(password), full_name, role),
        )
        conn.commit()
        flash(f"User '{username}' created.", "success")
    except Exception as e:
        conn.rollback()
        flash(str(e), "danger")
    conn.close()
    return redirect(url_for("users_page"))


@app.route("/users/toggle/<int:uid>", methods=["POST"])
@admin_required
def toggle_user(uid):
    conn = get_db()
    conn.execute("UPDATE users SET is_active = 1 - is_active WHERE id = %s", (uid,))
    conn.commit()
    conn.close()
    flash("User status updated.", "success")
    return redirect(url_for("users_page"))


@app.route("/users/delete/<int:uid>", methods=["POST"])
@admin_required
def delete_user(uid):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = %s", (uid,))
    conn.commit()
    conn.close()
    flash("User deleted.", "info")
    return redirect(url_for("users_page"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if login_user(username, password):
            return redirect(url_for("dashboard"))
        return redirect(url_for("login_page"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login_page"))


# ---------------------------------------------------------------- startup
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
