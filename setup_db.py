import sqlite3
import os

DB_PATH = "job_hunter.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table for user preferences
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_roles TEXT,
        min_salary INTEGER,
        locations TEXT,
        skills TEXT
    )
    ''')
    
    # Insert default row if table is empty
    cursor.execute("SELECT COUNT(*) FROM user_preferences")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
        INSERT INTO user_preferences (target_roles, min_salary, locations, skills)
        VALUES (?, ?, ?, ?)
        ''', ("AI Engineer, Python Backend Developer, SDE", 1000000, "Remote, Hyderabad, Bangalore", "Python, FastAPI, LangChain, Docker, LLMs"))
    
    # Table for scraped jobs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scraped_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        job_id TEXT UNIQUE,
        title TEXT,
        company TEXT,
        location TEXT,
        salary TEXT,
        job_url TEXT,
        match_reason TEXT,
        status TEXT DEFAULT 'new',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized successfully at {DB_PATH}")

if __name__ == "__main__":
    init_db()
