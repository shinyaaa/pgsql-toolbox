"""Shared constants for pgsql-toolbox."""

from pathlib import Path

PGSQL_DIR = Path.home() / "pgsql"
ARCHIVE_DIR = PGSQL_DIR / "_archive"
LOGS_DIR = PGSQL_DIR / "logs"
PORT_LOCK = PGSQL_DIR / "port_lock"
MAIN_REPO = PGSQL_DIR / "master" / "postgres"
REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "dashboard.db"
HIDDEN_DIRS = {"port_lock", "_archive", "logs", "master"}

SYNC_BRANCHES = [
    "REL_14_STABLE",
    "REL_15_STABLE",
    "REL_16_STABLE",
    "REL_17_STABLE",
    "REL_18_STABLE",
    "master",
]
GH_REPO = "shinyaaa/postgres"

# Port allocation for replication clusters
PRIMARY_PORT_MIN = 50000
PRIMARY_PORT_MAX = 50999
STANDBY_PORT_STRIDE = 1000
MAX_STANDBYS = 9
REPL_STREAMING_SYNC = "streaming_sync"
REPL_STREAMING_ASYNC = "streaming_async"
REPL_LOGICAL = "logical"
REPL_TYPES = [REPL_STREAMING_SYNC, REPL_STREAMING_ASYNC, REPL_LOGICAL]
REPL_STREAMING_TYPES = {REPL_STREAMING_SYNC, REPL_STREAMING_ASYNC}


def standby_port(primary_port: int, standby_index: int) -> int:
    """Derive standby port from primary port and index."""
    return primary_port + standby_index * STANDBY_PORT_STRIDE

# Log preview
LOG_PREVIEW_SIZE = 4096

# Claude Code startup polling in tmux
CLAUDE_STARTUP_TIMEOUT = 60
CLAUDE_STARTUP_POLL_INTERVAL = 1
CLAUDE_STARTUP_BUFFER = 2

# MCP server endpoint
MCP_ENDPOINT = "http://localhost:40000/mcp"
