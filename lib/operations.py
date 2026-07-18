"""Shared operations for pgsql-toolbox (archive, port_lock, pg_ctl, etc.)."""

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from lib.config import ARCHIVE_DIR, HIDDEN_DIRS, MAIN_REPO, PORT_LOCK, PGSQL_DIR
from lib.db import get_standbys, remove_standbys, update_branch_status

logger = logging.getLogger(__name__)

# Valid branch name: alphanumeric, hyphens, underscores, dots, slashes (no .., no leading /)
_BRANCH_NAME_RE = re.compile(r'^[A-Za-z0-9][\w.\-/]*$')

# A Claude Code cloud/teleport session id, e.g. "session_01ABC...". We keep the
# character class deliberately tight because the id is later typed into a shell
# as `claude --teleport <id>`, so it must never contain shell metacharacters.
_SESSION_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def validate_branch_name(name: str) -> str:
    """Validate and return the branch name, or raise ValueError."""
    if not name or not name.strip():
        raise ValueError("Branch name is required")
    name = name.strip()
    if '..' in name or name.startswith('/') or name.startswith('-'):
        raise ValueError(f"Invalid branch name: {name!r}")
    if not _BRANCH_NAME_RE.match(name):
        raise ValueError(f"Invalid branch name: {name!r}")
    return name


def normalize_teleport_session(raw: Optional[str]) -> Optional[str]:
    """Normalize a Claude Code teleport session identifier.

    Accepts either a bare session id ("session_01ABC...") or the full cloud
    session URL ("https://claude.ai/code/session_01ABC..."), and returns the
    bare id suitable for `claude --teleport <id>`. Returns None when the input
    is empty/whitespace (teleport not requested); raises ValueError when a
    non-empty value cannot be turned into a safe session id.
    """
    if not raw or not raw.strip():
        return None
    session = raw.strip()
    # If a cloud session URL was pasted, take the id after ".../code/",
    # dropping any query/fragment and trailing slash.
    if "claude.ai/code/" in session:
        session = session.split("claude.ai/code/", 1)[1]
        session = session.split("?", 1)[0].split("#", 1)[0].strip("/")
    if not _SESSION_ID_RE.match(session):
        raise ValueError(f"Invalid teleport session id: {raw!r}")
    return session


def run_cmd(cmd, check=True, capture=False, cwd=None, timeout=None,
            cmd_logger=None):
    """Run a subprocess command, logging the command and any output.

    Args:
        cmd: Command to run (list or string).
        check: If True, raise RuntimeError on non-zero exit.
        capture: If True, capture stdout/stderr separately (for programmatic use).
                 If False, merge stderr into stdout and log each line.
        cwd: Working directory.
        timeout: Timeout in seconds.
        cmd_logger: Logger instance to use (defaults to module logger).
    """
    log = cmd_logger or logger
    cmd_str = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    log.info(f"+ {cmd_str}")
    kwargs = {
        "cwd": cwd,
        "timeout": timeout,
        "text": True,
    }
    if capture:
        kwargs["capture_output"] = True
    else:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT
    result = subprocess.run(cmd, **kwargs)
    if not capture and result.stdout:
        for line in result.stdout.splitlines():
            log.info(line)
    if check and result.returncode != 0:
        if capture:
            error = (result.stderr or "") + (result.stdout or "")
        else:
            error = result.stdout or ""
        raise RuntimeError(f"Command failed (exit {result.returncode}): {cmd_str}\n{error}")
    return result


def make_run_wrapper(cmd_logger: logging.Logger):
    """Create a convenience wrapper that passes the given logger to run_cmd."""
    def _run(cmd, check=True, capture=False, cwd=None, timeout=None):
        return run_cmd(cmd, check=check, capture=capture, cwd=cwd,
                       timeout=timeout, cmd_logger=cmd_logger)
    return _run


def atomic_write(path: Path, content: str):
    """Atomically write content to a file using rename."""
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent))
    try:
        os.write(fd, content.encode())
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    else:
        os.close(fd)
        try:
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


def parse_port_lock() -> Dict[str, int]:
    """Parse port_lock file and return dict of project -> port."""
    result = {}
    if PORT_LOCK.exists():
        for line_no, line in enumerate(PORT_LOCK.read_text().splitlines(), 1):
            parts = line.strip().split()
            if not parts or parts[0].startswith("#"):
                continue
            if len(parts) < 2:
                logger.warning("port_lock line %d: too few fields: %s", line_no, line)
                continue
            try:
                port = int(parts[0])
            except ValueError:
                logger.warning("port_lock line %d: invalid port %r", line_no, parts[0])
                continue
            result[parts[1]] = port
    return result


def scan_worktrees() -> List[str]:
    """Scan ~/pgsql for existing worktree directories."""
    if not PGSQL_DIR.exists():
        return []
    skip = HIDDEN_DIRS
    return sorted(
        d.name
        for d in PGSQL_DIR.iterdir()
        if d.is_dir() and d.name not in skip
    )


def pg_ctl_path(name: str) -> Path:
    return PGSQL_DIR / name / "bin" / "pg_ctl"


def pg_data_path(name: str, standby_index: Optional[int] = None) -> Path:
    if standby_index is not None:
        return PGSQL_DIR / name / f"data-s{standby_index}"
    return PGSQL_DIR / name / "data"


def check_pg_running(name: str, standby_index: Optional[int] = None) -> Optional[str]:
    """Check if PostgreSQL is running for the given worktree.

    Args:
        name: Worktree/branch name
        standby_index: If set, check standby data-s{N} instead of primary data/

    Returns 'up', 'down', or None (no pg_ctl/data).
    """
    ctl = pg_ctl_path(name)
    data = pg_data_path(name, standby_index)
    if not ctl.exists() or not data.exists():
        return None
    result = subprocess.run(
        [str(ctl), "status", "-D", str(data)],
        capture_output=True, text=True,
    )
    return "up" if result.returncode == 0 else "down"


def remove_port_lock_entry(name: str):
    """Remove a branch's entry from the port_lock file."""
    if not PORT_LOCK.exists():
        return
    lines = PORT_LOCK.read_text().splitlines()
    new_lines = [
        line for line in lines
        if not (len(line.strip().split()) >= 2 and line.strip().split()[1] == name)
    ]
    if len(new_lines) != len(lines):
        atomic_write(PORT_LOCK, "\n".join(new_lines) + "\n" if new_lines else "")


def archive_branch(name: str, db_path: Optional[Path] = None) -> List[str]:
    """Archive a branch: stop PG, move to _archive, remove worktree/branches, update DB.

    Returns list of step descriptions.
    Raises RuntimeError on critical failure.
    """
    project_dir = PGSQL_DIR / name
    if not project_dir.exists():
        raise RuntimeError(f"Directory {name} not found")

    steps = []

    # 0. Stop standbys first (reverse order)
    standby_rows = get_standbys(name, db_path)
    ctl = pg_ctl_path(name)
    for sb in reversed(standby_rows):
        idx = sb["standby_index"]
        sb_data = pg_data_path(name, idx)
        if sb_data.exists() and ctl.exists():
            sb_status = check_pg_running(name, idx)
            if sb_status == "up":
                subprocess.run(
                    [str(ctl), "stop", "-D", str(sb_data), "-m", "fast"],
                    capture_output=True, text=True, timeout=30,
                )
                steps.append(f"Stopped standby S{idx}")

    # 1. Stop primary PostgreSQL if running
    pg_status = check_pg_running(name)
    if pg_status == "up":
        pgdata = pg_data_path(name)
        result = subprocess.run(
            [str(ctl), "stop", "-D", str(pgdata)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            steps.append("Stopped PostgreSQL")
        else:
            raise RuntimeError(
                f"Failed to stop PostgreSQL: {result.stdout + result.stderr}"
            )

    # 2. Kill tmux session if exists
    result = subprocess.run(
        ["tmux", "kill-session", "-t", name],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        steps.append(f"Killed tmux session: {name}")

    # 3. Move directory to _archive
    ARCHIVE_DIR.mkdir(exist_ok=True)
    dest = ARCHIVE_DIR / name
    if dest.exists():
        shutil.rmtree(str(dest))
    shutil.move(str(project_dir), str(dest))
    steps.append(f"Moved to _archive/{name}")

    # 4. Prune git worktree references
    if MAIN_REPO.exists():
        subprocess.run(
            ["git", "-C", str(MAIN_REPO), "worktree", "prune"],
            capture_output=True, text=True,
        )
        steps.append("Pruned worktree references")

        # 5. Delete local branch
        result = subprocess.run(
            ["git", "-C", str(MAIN_REPO), "branch", "-D", name],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            steps.append(f"Deleted local branch: {name}")
        else:
            steps.append(f"Local branch delete skipped: {result.stderr.strip()}")

        # 6. Delete remote branch
        result = subprocess.run(
            ["git", "-C", str(MAIN_REPO), "push", "origin", "--delete", name],
            capture_output=True, text=True,
            timeout=30,
        )
        if result.returncode == 0:
            steps.append(f"Deleted remote branch: {name}")
        else:
            steps.append(f"Remote branch delete skipped: {result.stderr.strip()}")

    # 7. Remove port_lock entry
    remove_port_lock_entry(name)
    steps.append("Removed port_lock entry")

    # 8. Remove standby records from DB
    if standby_rows:
        remove_standbys(name, db_path)
        steps.append("Removed standby records")

    # 9. Update DB status to archived
    update_branch_status(name, "archived", db_path)
    steps.append("Updated status to archived")

    return steps
