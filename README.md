# PresentKo

A simple local Wi-Fi classroom attendance system using Flask + MySQL.

## Main workflow

1. Teacher opens `/home`.
2. Teacher choose `Teacher` and Enter `username` and `password` given by admin.
3. Then imports one CSV for a specific class. The system creates the class, students, and enrollment records.
4. Teacher selects a class.
5. Students appear automatically in the teacher table.
6. Teacher clicks START ATTENDANCE.
7. Flask generates a 6-character code.
8. The session lasts 10 minutes.
9. Students open `/home` and choose `Student`. Then enter Student ID + PIN + code.
10. Flask verifies the student and records attendance.
11. Teacher dashboard refreshes every 2 seconds.
12. When 10 minutes ends, the session becomes inactive.
13. Teacher exports XLSX.
14. Export includes enrolled students; students without attendance are marked Absent.
15. The attendance session and attendance rows are deleted after export. Students, classes, and enrollment remain.

## CSV format

Required:
- student_id
- first_name
- last_name
- pin

Optional:
- course
- year_level

See `sample_students.csv`.

## Setup

### 1. Create the database

Run `schema.sql` in MySQL/SQLyog.

### 2. Install Python packages

```bash
pip install -r requirements.txt
```

### 3. Edit database credentials

Open `presentKo.py` and change:

```python
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "YOUR_MYSQL_PASSWORD",
    "database": "DATABASE_NAME"
}
```

### 4. Start Flask

```bash
python presentKo.py
```

Teacher:
`http://127.0.0.1:5000/Home`

Student:
`http://127.0.0.1:5000/Home`

For classroom Wi-Fi, students use the teacher laptop's LAN IP, for example:
`http://192.168.1.10:5000/Home`

## Important security note

This is a school-project prototype. Do not expose it directly to the public internet without adding proper authentication, HTTPS, CSRF protection, production server configuration, and other security controls.

The PIN is hashed with Werkzeug before it is stored in MySQL.

The device token is a browser cookie used only as a suspicious-activity signal. It is not a perfect device identity and should not be presented as foolproof anti-cheating.
