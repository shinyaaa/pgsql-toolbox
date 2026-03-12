"""Shared constants for pgsql-dashboard."""

from pathlib import Path

PGSQL_DIR = Path.home() / "pgsql"
ARCHIVE_DIR = PGSQL_DIR / "_archive"
LOGS_DIR = PGSQL_DIR / "logs"
PORT_LOCK = PGSQL_DIR / "port_lock"
MAIN_REPO = PGSQL_DIR / "master" / "postgres"
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "dashboard.db"

SYNC_BRANCHES = [
    "REL_14_STABLE",
    "REL_15_STABLE",
    "REL_16_STABLE",
    "REL_17_STABLE",
    "REL_18_STABLE",
    "master",
]
GH_REPO = "shinyaaa/postgres"
