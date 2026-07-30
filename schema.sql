-- ============================================================
-- YWAM Tailoring Training Centre Management System
-- PostgreSQL schema
--
-- Usage:
--   psql "$DATABASE_URL" -f schema.sql
--
-- This file is also applied automatically (idempotently) by
-- db.init_db() on app startup, so running it by hand is optional.
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id             SERIAL PRIMARY KEY,
    username       TEXT UNIQUE NOT NULL,
    password_hash  TEXT NOT NULL,
    full_name      TEXT,
    role           TEXT DEFAULT 'Staff',
    is_active      INTEGER DEFAULT 1,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    id                    SERIAL PRIMARY KEY,
    name                  TEXT NOT NULL,
    dob                   TEXT,
    age                   INTEGER,
    gender                TEXT,
    marital_status        TEXT,
    father_husband_name   TEXT,
    mother_name           TEXT,
    education             TEXT,
    occupation            TEXT,
    employment_status     TEXT,
    community             TEXT,
    religion              TEXT,
    family_income         TEXT,
    special_skill         TEXT,
    prev_experience       TEXT,
    course                TEXT,
    batch                 TEXT,
    address               TEXT,
    mobile                TEXT,
    alt_mobile            TEXT,
    email                 TEXT,
    emergency_name        TEXT,
    emergency_relation    TEXT,
    emergency_mobile      TEXT,
    admission_date        TEXT,
    start_date            TEXT,
    end_date              TEXT,
    duration_months       INTEGER DEFAULT 3,
    monthly_fee           REAL DEFAULT 0,
    status                TEXT DEFAULT 'Active',
    device_user_id        TEXT,
    photo_filename        TEXT,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attendance (
    id          SERIAL PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    status      TEXT NOT NULL,
    source      TEXT DEFAULT 'Manual',
    UNIQUE (student_id, date)
);

CREATE TABLE IF NOT EXISTS staff_attendance (
    id        SERIAL PRIMARY KEY,
    staff_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date      TEXT NOT NULL,
    status    TEXT NOT NULL,
    UNIQUE (staff_id, date)
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE TABLE IF NOT EXISTS fees (
    id            SERIAL PRIMARY KEY,
    student_id    INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    month         TEXT NOT NULL,
    amount_paid   REAL NOT NULL DEFAULT 0,
    payment_date  TEXT,
    mode          TEXT,
    remarks       TEXT
);

CREATE TABLE IF NOT EXISTS certificates (
    id                SERIAL PRIMARY KEY,
    student_id        INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    duration_months   INTEGER NOT NULL,
    start_date        TEXT,
    end_date          TEXT,
    issued_on         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default admin user (username: ywam / password: 1974)
-- password_hash is sha256("1974")
INSERT INTO users (username, password_hash, full_name, role)
VALUES ('ywam', 'ec54e99514663edb97adef400fbf34a77daae108303d3da8008a7dfb4cdf0f52', 'YWAM Administrator', 'Admin')
ON CONFLICT (username) DO NOTHING;
