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
    try:
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS standbys (
                primary_name TEXT NOT NULL,
                standby_index INTEGER NOT NULL,
                repl_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (primary_name, standby_index)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def update_branch_status(name: str, status: str, db_path: Optional[Path] = None):
    """Update a branch's status in the database."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE branches SET status = ?, updated_at = ? WHERE name = ?",
            (status, datetime.now().isoformat(), name),
        )
        conn.commit()
    finally:
        conn.close()


def get_standbys(name: str, db_path: Optional[Path] = None) -> list:
    """Get standby records for a primary branch."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT standby_index, repl_type, created_at FROM standbys "
            "WHERE primary_name = ? ORDER BY standby_index",
            (name,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_standby(primary_name: str, standby_index: int, repl_type: str,
                db_path: Optional[Path] = None):
    """Add a standby record for a primary branch."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO standbys (primary_name, standby_index, repl_type) "
            "VALUES (?, ?, ?)",
            (primary_name, standby_index, repl_type),
        )
        conn.commit()
    finally:
        conn.close()


def remove_standbys(primary_name: str, db_path: Optional[Path] = None):
    """Remove all standby records for a primary branch."""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "DELETE FROM standbys WHERE primary_name = ?",
            (primary_name,),
        )
        conn.commit()
    finally:
        conn.close()
