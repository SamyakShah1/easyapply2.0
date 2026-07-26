"""
tracker.py — Job Application Tracker
Logs every application to a local SQLite database and keeps applications.csv in sync.
"""
import sqlite3
import csv
import json
import os
import sys
from datetime import datetime

# Force UTF-8 on Windows terminal (prevents charmap crash from Unicode chars)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = os.path.join(os.path.dirname(__file__), "applications.db")
CSV_PATH = os.path.join(os.path.dirname(__file__), "applications.csv")

COLUMNS = [
    "id", "applied_at", "platform", "company", "job_title",
    "job_url", "location", "salary_range", "status",
    "resume_used", "notes"
]

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create the applications table if it doesn't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                applied_at  TEXT NOT NULL,
                platform    TEXT NOT NULL,
                company     TEXT NOT NULL,
                job_title   TEXT NOT NULL,
                job_url     TEXT NOT NULL,
                location    TEXT DEFAULT 'Not Specified',
                salary_range TEXT DEFAULT 'Not Specified',
                status      TEXT DEFAULT 'Applied',
                resume_used TEXT DEFAULT '',
                notes       TEXT DEFAULT ''
            )
        """)
        conn.commit()

def log_application(
    platform: str,
    company: str,
    job_title: str,
    job_url: str,
    location: str = "Not Specified",
    salary_range: str = "Not Specified",
    status: str = "Applied",
    resume_used: str = "",
    notes: str = ""
) -> int:
    """
    Insert a new application row. Returns the new row id.
    Also refreshes applications.csv.
    """
    init_db()
    applied_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as conn:
        cur = conn.execute("""
            INSERT INTO applications
                (applied_at, platform, company, job_title, job_url,
                 location, salary_range, status, resume_used, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (applied_at, platform, company, job_title, job_url,
              location, salary_range, status, resume_used, notes))
        conn.commit()
        row_id = cur.lastrowid

    export_csv()
    print(f"[Tracker] ✓ Logged: '{job_title}' @ '{company}' [{platform}] → ID #{row_id}")
    return row_id

def update_status(job_url: str, new_status: str):
    """Update the status of an application by job URL."""
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE applications SET status = ? WHERE job_url = ?",
            (new_status, job_url)
        )
        conn.commit()
    export_csv()
    print(f"[Tracker] Status updated → '{new_status}' for {job_url}")

def get_all() -> list[dict]:
    """Return all applications as a list of dicts, newest first."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def get_stats() -> dict:
    """Return aggregate stats for the dashboard."""
    init_db()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        by_status = dict(conn.execute(
            "SELECT status, COUNT(*) FROM applications GROUP BY status"
        ).fetchall())
        by_platform = dict(conn.execute(
            "SELECT platform, COUNT(*) FROM applications GROUP BY platform"
        ).fetchall())
        # Last 14 days daily counts
        daily = conn.execute("""
            SELECT DATE(applied_at) as day, COUNT(*) as cnt
            FROM applications
            WHERE applied_at >= DATE('now', '-13 days')
            GROUP BY day
            ORDER BY day
        """).fetchall()

    return {
        "total": total,
        "by_status": by_status,
        "by_platform": by_platform,
        "daily": [{"day": r[0], "cnt": r[1]} for r in daily],
    }

def export_csv():
    """Write all applications to applications.csv."""
    rows = get_all()
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

# Initialise on import
init_db()
