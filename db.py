import sqlite3
from datetime import date

DB_FILE = "applications.db"

STATUSES = ["Applied", "OA", "Interview", "Offer", "Rejected", "Withdrawn"]


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('Internship', 'Graduate')),
                status TEXT NOT NULL DEFAULT 'Applied',
                date_applied TEXT NOT NULL,
                notes TEXT,
                url TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cached_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                title TEXT,
                company TEXT,
                location TEXT,
                description TEXT,
                url TEXT,
                type TEXT,
                posted_at TEXT,
                fetched_at TEXT NOT NULL,
                is_new INTEGER NOT NULL DEFAULT 1
            )
        """)


def add_application(company, role, app_type, status="Applied", notes="", url=""):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO applications (company, role, type, status, date_applied, notes, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (company, role, app_type, status, str(date.today()), notes, url),
        )
        return cur.lastrowid


def get_applications(status_filter=None, type_filter=None):
    query = "SELECT * FROM applications WHERE 1=1"
    params = []
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if type_filter:
        query += " AND type = ?"
        params.append(type_filter)
    query += " ORDER BY date_applied DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def update_status(app_id, new_status):
    with get_conn() as conn:
        cur = conn.execute("UPDATE applications SET status = ? WHERE id = ?", (new_status, app_id))
        return cur.rowcount > 0


def delete_application(app_id):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        return cur.rowcount > 0


def save_cached_jobs(jobs: list[dict], fetched_at: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM cached_jobs")
        conn.executemany(
            "INSERT INTO cached_jobs (source, title, company, location, description, url, type, posted_at, fetched_at, is_new) VALUES (?,?,?,?,?,?,?,?,?,1)",
            [(j["source"], j["title"], j["company"], j["location"], j["description"], j["url"], j["type"], j.get("posted_at", ""), fetched_at) for j in jobs],
        )


def get_cached_jobs() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM cached_jobs ORDER BY id DESC").fetchall()]


def get_new_job_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM cached_jobs WHERE is_new = 1").fetchone()[0]


def get_last_fetched() -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT fetched_at FROM cached_jobs ORDER BY id DESC LIMIT 1").fetchone()
        return row[0] if row else None


def mark_jobs_seen():
    with get_conn() as conn:
        conn.execute("UPDATE cached_jobs SET is_new = 0")
