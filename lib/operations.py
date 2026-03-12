"""Shared operations for pgsql-dashboard (archive, port_lock, pg_ctl, etc.)."""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from lib.config import ARCHIVE_DIR, MAIN_REPO, PORT_LOCK, PGSQL_DIR
from lib.db import update_branch_status


def parse_port_lock() -> dict[str, int]:
    """Parse port_lock file and return dict of project -> port."""
    result = {}
    if PORT_LOCK.exists():
        for line in PORT_LOCK.read_text().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and not parts[0].startswith("#"):
                port, project = parts[0], parts[1]
                result[project] = int(port)
    return result


def scan_worktrees() -> list[str]:
    """Scan ~/pgsql for existing worktree directories."""
    if not PGSQL_DIR.exists():
        return []
    skip = {"port_lock", "_archive", "logs"}
    return sorted(
        d.name
        for d in PGSQL_DIR.iterdir()
        if d.is_dir() and d.name not in skip
    )


def pg_ctl_path(name: str) -> Path:
    return PGSQL_DIR / name / "bin" / "pg_ctl"


def pg_data_path(name: str) -> Path:
    return PGSQL_DIR / name / "data"


def check_pg_running(name: str) -> Optional[str]:
    """Check if PostgreSQL is running for the given worktree.
    Returns 'up', 'down', or None (no pg_ctl/data)."""
    ctl = pg_ctl_path(name)
    data = pg_data_path(name)
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
        PORT_LOCK.write_text("\n".join(new_lines) + "\n" if new_lines else "")


def archive_branch(name: str, db_path: Optional[Path] = None) -> list:
    """Archive a branch: stop PG, move to _archive, remove worktree/branches, update DB.

    Returns list of step descriptions.
    Raises RuntimeError on critical failure.
    """
    project_dir = PGSQL_DIR / name
    if not project_dir.exists():
        raise RuntimeError(f"Directory {name} not found")

    steps = []

    # 1. Stop PostgreSQL if running
    pg_status = check_pg_running(name)
    if pg_status == "up":
        ctl = pg_ctl_path(name)
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

    # 8. Update DB status to archived
    update_branch_status(name, "archived", db_path)
    steps.append("Updated status to archived")

    return steps
