"""
db.py - Database setup and helper functions for
YWAM Tailoring Training Centre Management System

PostgreSQL only. Configure the connection via the DATABASE_URL
environment variable, e.g.:

    postgresql://user:password@localhost:5432/tailoring_center

If DATABASE_URL is not set, a local default is used (see DEFAULT_DATABASE_URL
below) so the app still boots in dev, but you should always set DATABASE_URL
explicitly in production.
"""
import os

import psycopg2
import psycopg2.extras

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/tailoring_center"
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL


def _pg_conn():
    return psycopg2.connect(DATABASE_URL)


class _ConnWrapper:
    """Thin wrapper so call sites can chain .execute(...).fetchone()/.fetchall()
    the same way they could with sqlite3, while using a real psycopg2
    DictCursor under the hood."""

    def __init__(self, raw):
        self._raw = raw
        self._cur = None
        raw.autocommit = False

    def _get_cursor(self):
        if self._cur is None or self._cur.closed:
            self._cur = self._raw.cursor(cursor_factory=psycopg2.extras.DictCursor)
        return self._cur

    def execute(self, sql, params=None):
        cur = self._get_cursor()
        cur.execute(sql, params or ())
        self._cur = cur
        return self

    def fetchone(self):
        row = self._get_cursor().fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self._get_cursor().fetchall()]

    def commit(self):
        self._raw.commit()

    def rollback(self):
        try:
            self._raw.rollback()
        except Exception:
            pass

    def close(self):
        if self._cur and not self._cur.closed:
            self._cur.close()
        try:
            self._raw.close()
        except Exception:
            pass

    def __iter__(self):
        return iter(self._get_cursor())

    def __next__(self):
        return next(self._get_cursor())

    def __getattr__(self, name):
        return getattr(self._raw, name)


def get_db():
    return _ConnWrapper(_pg_conn())


def init_db():
    """Create all tables (if they don't already exist) and seed the
    default admin user. Safe to run repeatedly."""
    conn = get_db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        role TEXT DEFAULT 'Staff',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    import hashlib
    default_hash = hashlib.sha256("1974".encode()).hexdigest()
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role) "
        "VALUES (%s,%s,%s,%s) ON CONFLICT (username) DO NOTHING",
        ("ywam", default_hash, "YWAM Administrator", "Admin"),
    )

    conn.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        dob TEXT,
        age INTEGER,
        gender TEXT,
        marital_status TEXT,
        father_husband_name TEXT,
        mother_name TEXT,
        education TEXT,
        occupation TEXT,
        employment_status TEXT,
        community TEXT,
        religion TEXT,
        family_income TEXT,
        special_skill TEXT,
        prev_experience TEXT,
        course TEXT,
        batch TEXT,
        address TEXT,
        mobile TEXT,
        alt_mobile TEXT,
        email TEXT,
        emergency_name TEXT,
        emergency_relation TEXT,
        emergency_mobile TEXT,
        admission_date TEXT,
        start_date TEXT,
        end_date TEXT,
        duration_months INTEGER DEFAULT 3,
        monthly_fee REAL DEFAULT 0,
        status TEXT DEFAULT 'Active',
        device_user_id TEXT,
        photo_filename TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id SERIAL PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        date TEXT NOT NULL,
        status TEXT NOT NULL,
        source TEXT DEFAULT 'Manual',
        UNIQUE(student_id, date)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS staff_attendance (
        id SERIAL PRIMARY KEY,
        staff_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date TEXT NOT NULL,
        status TEXT NOT NULL,
        UNIQUE(staff_id, date)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS fees (
        id SERIAL PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        month TEXT NOT NULL,
        amount_paid REAL NOT NULL DEFAULT 0,
        payment_date TEXT,
        mode TEXT,
        remarks TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS certificates (
        id SERIAL PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        duration_months INTEGER NOT NULL,
        start_date TEXT,
        end_date TEXT,
        issued_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Idempotent column additions for upgrades from older schemas.
    conn.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS device_user_id TEXT")
    conn.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS photo_filename TEXT")
    conn.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'Manual'")

    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads", "photos"), exist_ok=True)

    conn.commit()
    conn.close()


PHOTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads", "photos")


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_user_by_username(conn, username):
    return conn.execute("SELECT * FROM users WHERE username = %s", (username,)).fetchone()


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
