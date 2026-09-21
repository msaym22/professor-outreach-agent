import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
from config import STATE_DB_PATH, BASE_DIR

JSON_STATE_PATH = BASE_DIR / ".agent_state.json"


def get_db_connection():
    conn = sqlite3.connect(STATE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS seen_urls (
            url TEXT PRIMARY KEY,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS agent_flags (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # sent_emails tracks professors already emailed (by email address)
    c.execute('''
        CREATE TABLE IF NOT EXISTS sent_emails (
            email TEXT PRIMARY KEY,
            prof_name TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # contacted_domains prevents spamming same university department
    c.execute('''
        CREATE TABLE IF NOT EXISTS contacted_domains (
            domain TEXT PRIMARY KEY,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # retry_log: avoids re-hitting APIs for known dead-end URLs
    c.execute('''
        CREATE TABLE IF NOT EXISTS retry_log (
            url          TEXT PRIMARY KEY,
            retry_count  INTEGER DEFAULT 0,
            last_retried TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            exhausted    INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()


def get_flag(key, default=None):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM agent_flags WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def set_flag(key, value):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO agent_flags (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()


def add_seen_url(url, status=""):
    if not url:
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO seen_urls (url, status) VALUES (?, ?)', (url, status))
    conn.commit()
    conn.close()


def is_url_seen(url):
    if not url:
        return False
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM seen_urls WHERE url = ?', (url,))
    row = c.fetchone()
    conn.close()
    return bool(row)


def get_all_seen_urls():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT url FROM seen_urls')
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]


def mark_email_sent(email, prof_name=""):
    if not email:
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        'INSERT OR IGNORE INTO sent_emails (email, prof_name) VALUES (?, ?)',
        (email, prof_name)
    )
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if domain:
        c.execute(
            'INSERT OR IGNORE INTO contacted_domains (domain) VALUES (?)',
            (domain,)
        )
    conn.commit()
    conn.close()


def has_emailed(email):
    if not email:
        return False
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM sent_emails WHERE email = ?', (email,))
    row = c.fetchone()
    conn.close()
    return bool(row)


def can_run_serp_today():
    today = datetime.now().strftime("%Y-%m-%d")
    return get_flag("serp_last_run_date") != today


def mark_serp_ran():
    set_flag("serp_last_run_date", datetime.now().strftime("%Y-%m-%d"))


MAX_RETRY_ATTEMPTS    = 3
RETRY_COOLDOWN_HOURS  = 24


def can_retry_url(url):
    if not url:
        return False
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT retry_count, last_retried, exhausted FROM retry_log WHERE url = ?', (url,))
    row = c.fetchone()
    conn.close()

    if not row:
        return True
    if row["exhausted"]:
        return False
    if row["retry_count"] >= MAX_RETRY_ATTEMPTS:
        _mark_retry_exhausted(url)
        return False

    try:
        last = datetime.strptime(row["last_retried"], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - last).total_seconds() / 3600 < RETRY_COOLDOWN_HOURS:
            return False
    except Exception:
        pass
    return True


def record_retry_attempt(url):
    if not url:
        return
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO retry_log (url, retry_count, last_retried, exhausted)
        VALUES (?, 1, ?, 0)
        ON CONFLICT(url) DO UPDATE SET
            retry_count  = retry_count + 1,
            last_retried = excluded.last_retried
    ''', (url, now_str))
    conn.commit()
    conn.close()


def _mark_retry_exhausted(url):
    if not url:
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO retry_log (url, retry_count, exhausted)
        VALUES (?, ?, 1)
        ON CONFLICT(url) DO UPDATE SET exhausted = 1
    ''', (url, MAX_RETRY_ATTEMPTS))
    conn.commit()
    conn.close()


def mark_retry_success(url):
    if not url:
        return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('DELETE FROM retry_log WHERE url = ?', (url,))
    conn.commit()
    conn.close()


# Initialise on import
init_db()
