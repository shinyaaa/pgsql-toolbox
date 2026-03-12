"""Flask-independent SQLite helpers."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from lib.config import DB_PATH


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a standalone SQLite connection (no Flask dependency)."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: Optional[Path] = None):
    """Create the branches table if it doesn't exist."""
    conn = get_connection(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS branches (
            name TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'active',
            mailing_list_url TEXT DEFAULT '',
            commitfest_url TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def update_branch_status(name: str, status: str, db_path: Optional[Path] = None):
    """Update a branch's status in the database."""
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE branches SET status = ?, updated_at = ? WHERE name = ?",
        (status, datetime.now().isoformat(), name),
    )
    conn.commit()
    conn.close()
