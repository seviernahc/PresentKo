CREATE DATABASE IF NOT EXISTS smartattend;
USE smartattend;

CREATE TABLE student (
    student_id VARCHAR(20) PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    course VARCHAR(100),
    year_level INT,
    pin_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE class (
    class_id INT AUTO_INCREMENT PRIMARY KEY,
    class_name VARCHAR(60) NOT NULL,
    school_year VARCHAR(20) NOT NULL,
    semester VARCHAR(20) NOT NULL,
    UNIQUE (class_name, school_year, semester)
);

CREATE TABLE enrollment (
    enrollment_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    class_id INT NOT NULL,
    enrolled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_enrollment_student
        FOREIGN KEY (student_id) REFERENCES student(student_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_enrollment_class
        FOREIGN KEY (class_id) REFERENCES class(class_id)
        ON DELETE CASCADE,

    UNIQUE (student_id, class_id)
);

CREATE TABLE attendance_session (
    session_id INT AUTO_INCREMENT PRIMARY KEY,
    class_id INT NOT NULL,
    attendance_code VARCHAR(10) NOT NULL UNIQUE,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_session_class
        FOREIGN KEY (class_id) REFERENCES class(class_id)
        ON DELETE CASCADE
);

CREATE TABLE attendance (
    attendance_id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    student_id VARCHAR(20) NOT NULL,
    time_in DATETIME NOT NULL,
    status ENUM('Present', 'Late') NOT NULL,
    device_token VARCHAR(255),
    is_flagged BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT fk_attendance_session
        FOREIGN KEY (session_id) REFERENCES attendance_session(session_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_attendance_student
        FOREIGN KEY (student_id) REFERENCES student(student_id)
        ON DELETE CASCADE,

    UNIQUE (session_id, student_id)
);
