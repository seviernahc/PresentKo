from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets
import string
import pandas as pd
from io import BytesIO
import uuid

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Root@123",
    "database": "presentko"
}

ATTENDANCE_MINUTES = 10
LATE_AFTER_MINUTES = 5


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def generate_code(length=6):
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def get_device_token():
    token = request.cookies.get("smartattend_device")
    if not token:
        token = str(uuid.uuid4())
    return token


def finish_expired_sessions(cursor):
    cursor.execute("""
        UPDATE attendance_session
        SET is_active = FALSE
        WHERE is_active = TRUE AND end_time <= NOW()
    """)


@app.route("/")
def index():
    return render_template('base.html')


@app.route("/teacher")
def teacher_dashboard():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        finish_expired_sessions(cursor)
        db.commit()

        cursor.execute("""
            SELECT c.class_id, c.class_name, c.school_year, c.semester,
                   COUNT(e.enrollment_id) AS student_count
            FROM class c
            LEFT JOIN enrollment e ON c.class_id = e.class_id
            GROUP BY c.class_id
            ORDER BY c.class_name
        """)
        classes = cursor.fetchall()

        selected_id = request.args.get("class_id", type=int)
        selected_class = None
        students = []
        active_session = None

        if selected_id:
            cursor.execute("""
                SELECT class_id, class_name, school_year, semester
                FROM class
                WHERE class_id = %s
            """, (selected_id,))
            selected_class = cursor.fetchone()

            if selected_class:
                cursor.execute("""
                    SELECT s.student_id, s.first_name, s.last_name
                    FROM student s
                    JOIN enrollment e ON s.student_id = e.student_id
                    WHERE e.class_id = %s
                    ORDER BY s.last_name, s.first_name
                """, (selected_id,))
                students = cursor.fetchall()

                cursor.execute("""
                    SELECT session_id, attendance_code, start_time, end_time, is_active
                    FROM attendance_session
                    WHERE class_id = %s AND is_active = TRUE
                    ORDER BY session_id DESC
                    LIMIT 1
                """, (selected_id,))
                active_session = cursor.fetchone()

        return render_template(
            "teacher.html",
            classes=classes,
            selected_class=selected_class,
            students=students,
            active_session=active_session
        )
    finally:
        cursor.close()
        db.close()


@app.route("/import-class", methods=["POST"])
def import_class():
    uploaded = request.files.get("csv_file")
    class_name = request.form.get("class_name", "").strip()
    school_year = request.form.get("school_year", "").strip()
    semester = request.form.get("semester", "").strip()

    if not uploaded or uploaded.filename == "":
        flash("Please choose a CSV file.")
        return redirect(url_for("teacher_dashboard"))

    if not class_name or not school_year or not semester:
        flash("Class name, school year, and semester are required.")
        return redirect(url_for("teacher_dashboard"))

    try:
        df = pd.read_csv(uploaded)

        required = {"student_id", "first_name", "last_name", "pin"}
        missing = required - set(df.columns)
        if missing:
            flash("Missing CSV columns: " + ", ".join(sorted(missing)))
            return redirect(url_for("teacher_dashboard"))

        db = get_db_connection()
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO class (class_name, school_year, semester)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE class_id = LAST_INSERT_ID(class_id)
        """, (class_name, school_year, semester))
        class_id = cursor.lastrowid

        for _, row in df.iterrows():
            student_id = str(row["student_id"]).strip()
            first_name = str(row["first_name"]).strip()
            last_name = str(row["last_name"]).strip()
            pin = str(row["pin"]).strip()

            if not student_id or not first_name or not last_name or not pin:
                continue

            course = str(row["course"]).strip() if "course" in df.columns and pd.notna(row["course"]) else None
            year_level = int(row["year_level"]) if "year_level" in df.columns and pd.notna(row["year_level"]) else None

            cursor.execute("""
                INSERT INTO student
                    (student_id, first_name, last_name, course, year_level, pin_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    first_name = VALUES(first_name),
                    last_name = VALUES(last_name),
                    course = VALUES(course),
                    year_level = VALUES(year_level)
            """, (
                student_id, first_name, last_name, course, year_level,
                generate_password_hash(pin)
            ))

            cursor.execute("""
                INSERT IGNORE INTO enrollment (student_id, class_id)
                VALUES (%s, %s)
            """, (student_id, class_id))

        db.commit()
        flash(f"Class imported successfully. {len(df)} CSV rows processed.")
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        flash(f"Import error: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()

    return redirect(url_for("teacher_dashboard", class_id=class_id if 'class_id' in locals() else None))


@app.route("/start-attendance/<int:class_id>", methods=["POST"])
def start_attendance(class_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        finish_expired_sessions(cursor)

        cursor.execute("""
            SELECT session_id FROM attendance_session
            WHERE class_id = %s AND is_active = TRUE
            LIMIT 1
        """, (class_id,))
        if cursor.fetchone():
            flash("This class already has an active attendance session.")
            return redirect(url_for("teacher_dashboard", class_id=class_id))

        now = datetime.now()
        end = now + timedelta(minutes=ATTENDANCE_MINUTES)
        code = generate_code()

        cursor.execute("""
            INSERT INTO attendance_session
                (class_id, attendance_code, start_time, end_time, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
        """, (class_id, code, now, end))

        db.commit()
        session_id = cursor.lastrowid

        flash(f"Attendance started. Code: {code}")
        return redirect(url_for("teacher_dashboard", class_id=class_id))
    finally:
        cursor.close()
        db.close()


@app.route("/teacher/session/<int:session_id>/data")
def session_data(session_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        finish_expired_sessions(cursor)
        db.commit()

        cursor.execute("""
            SELECT a.student_id, s.first_name, s.last_name,
                   a.time_in, a.status, a.is_flagged
            FROM attendance a
            JOIN student s ON a.student_id = s.student_id
            WHERE a.session_id = %s
            ORDER BY a.time_in
        """, (session_id,))
        attendance_rows = cursor.fetchall()

        cursor.execute("""
            SELECT c.class_name, ses.start_time, ses.end_time, ses.is_active
            FROM attendance_session ses
            JOIN class c ON ses.class_id = c.class_id
            WHERE ses.session_id = %s
        """, (session_id,))
        session = cursor.fetchone()

        if not session:
            return {"error": "Session not found"}, 404

        return {
            "session": {
                "class_name": session["class_name"],
                "start_time": session["start_time"].isoformat(),
                "end_time": session["end_time"].isoformat(),
                "is_active": bool(session["is_active"])
            },
            "attendance": [
                {
                    "student_id": row["student_id"],
                    "name": f'{row["first_name"]} {row["last_name"]}',
                    "time_in": row["time_in"].strftime("%Y-%m-%d %H:%M:%S"),
                    "status": row["status"],
                    "is_flagged": bool(row["is_flagged"])
                }
                for row in attendance_rows
            ]
        }
    finally:
        cursor.close()
        db.close()


@app.route("/end-attendance/<int:session_id>", methods=["POST"])
def end_attendance(session_id):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE attendance_session
            SET is_active = FALSE, end_time = LEAST(end_time, NOW())
            WHERE session_id = %s
        """, (session_id,))
        db.commit()
        flash("Attendance ended.")
    finally:
        cursor.close()
        db.close()
    return redirect(url_for("teacher_dashboard"))


@app.route("/student")
def student_page():
    return render_template("student_index.html")


@app.route("/submit-attendance", methods=["POST"])
def submit_attendance():
    student_id = request.form.get("student_id", "").strip()
    pin = request.form.get("pin", "").strip()
    code = request.form.get("attendance_code", "").strip().upper()

    if not student_id or not pin or not code:
        return render_template("student_index.html", error="Please complete all fields.")

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        finish_expired_sessions(cursor)
        db.commit()

        cursor.execute("""
            SELECT student_id, pin_hash
            FROM student
            WHERE student_id = %s
        """, (student_id,))
        student = cursor.fetchone()

        if not student or not check_password_hash(student["pin_hash"], pin):
            return render_template("student_index.html", error="Invalid Student ID or PIN.")

        cursor.execute("""
            SELECT session_id, class_id, start_time, end_time
            FROM attendance_session
            WHERE attendance_code = %s
              AND is_active = TRUE
              AND start_time <= NOW()
              AND end_time > NOW()
            LIMIT 1
        """, (code,))
        session = cursor.fetchone()

        if not session:
            return render_template("student_index.html", error="Invalid or expired attendance code.")

        cursor.execute("""
            SELECT enrollment_id
            FROM enrollment
            WHERE student_id = %s AND class_id = %s
        """, (student_id, session["class_id"]))

        if not cursor.fetchone():
            return render_template("student_index.html", error="You are not enrolled in this class.")

        cursor.execute("""
            SELECT attendance_id
            FROM attendance
            WHERE session_id = %s AND student_id = %s
        """, (session["session_id"], student_id))

        if cursor.fetchone():
            return render_template("student_index.html", error="You already submitted attendance.")

        now = datetime.now()
        late_limit = session["start_time"] + timedelta(minutes=LATE_AFTER_MINUTES)
        status = "Present" if now <= late_limit else "Late"

        device_token = get_device_token()

        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM attendance
            WHERE session_id = %s AND device_token = %s
        """, (session["session_id"], device_token))
        same_device = cursor.fetchone()["count"]

        is_flagged = same_device > 0

        cursor.execute("""
            INSERT INTO attendance
                (session_id, student_id, time_in, status, device_token, is_flagged)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            session["session_id"], student_id, now,
            status, device_token, is_flagged
        ))

        db.commit()

        response = make_response(render_template(
            "student_index.html",
            success=f"Attendance recorded successfully. Status: {status}"
        ))
        response.set_cookie(
            "smartattend_device",
            device_token,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax"
        )
        return response

    except Error as e:
        db.rollback()
        return render_template("student_index.html", error=f"Database error: {e}")
    finally:
        cursor.close()
        db.close()


@app.route("/export/<int:session_id>")
def export_attendance(session_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT ses.session_id, c.class_name, c.school_year, c.semester,
                   ses.attendance_code, ses.start_time, ses.end_time
            FROM attendance_session ses
            JOIN class c ON ses.class_id = c.class_id
            WHERE ses.session_id = %s
        """, (session_id,))
        session = cursor.fetchone()

        if not session:
            return "Session not found.", 404

        cursor.execute("""
            SELECT s.student_id, s.first_name, s.last_name,
                   a.time_in, a.status, a.is_flagged
            FROM enrollment e
            JOIN student s ON e.student_id = s.student_id
            LEFT JOIN attendance a
              ON a.student_id = s.student_id
             AND a.session_id = %s
            WHERE e.class_id = (
                SELECT class_id FROM attendance_session WHERE session_id = %s
            )
            ORDER BY s.last_name, s.first_name
        """, (session_id, session_id))
        rows = cursor.fetchall()

        data = []
        for row in rows:
            status = row["status"] if row["status"] else "Absent"
            data.append({
                "Student ID": row["student_id"],
                "First Name": row["first_name"],
                "Last Name": row["last_name"],
                "Time In": row["time_in"].strftime("%Y-%m-%d %H:%M:%S") if row["time_in"] else "",
                "Status": status,
                "Suspicious": "Yes" if row["is_flagged"] else "No"
            })

        df = pd.DataFrame(data)

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Attendance")

        output.seek(0)

        # Delete only the session/attendance data after the XLSX is prepared.
        # Student, class, and enrollment records remain for future attendance.
        cursor.execute("""
            DELETE FROM attendance_session
            WHERE session_id = %s
        """, (session_id,))
        db.commit()

        filename = f'{session["class_name"]}_attendance_{session["session_id"]}.xlsx'
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        cursor.close()
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
