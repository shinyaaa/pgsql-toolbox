#!/usr/bin/env python3
"""PostgreSQL Worktree Dashboard Server."""

import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

app = Flask(__name__)

PGSQL_DIR = Path.home() / "pgsql"
ARCHIVE_DIR = PGSQL_DIR / "_archive"
LOGS_DIR = PGSQL_DIR / "logs"
PORT_LOCK = PGSQL_DIR / "port_lock"
MAIN_REPO = PGSQL_DIR / "master" / "postgres"
PG_INIT = Path.home() / "git" / "settings" / "bin" / "pg_init"
DB_PATH = Path(__file__).parent / "dashboard.db"

# Track background pg_init tasks: branch_name -> {"status": "running"/"done"/"error", "error": "..."}
pg_init_tasks = {}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.execute("""
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
    db.commit()
    db.close()


def parse_port_lock():
    """Parse port_lock file and return dict of branch -> port."""
    result = {}
    if PORT_LOCK.exists():
        for line in PORT_LOCK.read_text().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and not parts[0].startswith("#"):
                port, project = parts[0], parts[1]
                result[project] = int(port)
    return result


def scan_worktrees():
    """Scan ~/pgsql for existing worktree directories."""
    if not PGSQL_DIR.exists():
        return []
    return sorted(
        d.name
        for d in PGSQL_DIR.iterdir()
        if d.is_dir() and d.name not in ("port_lock", "_archive")
    )


def pg_ctl_path(name):
    return PGSQL_DIR / name / "bin" / "pg_ctl"


def pg_data_path(name):
    return PGSQL_DIR / name / "data"


def check_pg_running(name):
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


def sync_branches():
    """Sync filesystem state with database."""
    db = get_db()
    worktrees = scan_worktrees()
    port_map = parse_port_lock()

    for name in worktrees:
        existing = db.execute(
            "SELECT name FROM branches WHERE name = ?", (name,)
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO branches (name, status) VALUES (?, 'active')",
                (name,),
            )
    db.commit()

    rows = db.execute("SELECT * FROM branches ORDER BY name").fetchall()
    branches = []
    for row in rows:
        d = dict(row)
        d["port"] = port_map.get(d["name"])
        d["exists_on_disk"] = d["name"] in worktrees
        src_dir = PGSQL_DIR / d["name"] / "postgres"
        d["src_dir"] = str(src_dir) if src_dir.exists() else None
        d["pg_running"] = check_pg_running(d["name"]) if d["exists_on_disk"] else None
        branches.append(d)
    return branches


# --- Status definitions ---
STATUSES = [
    "active",
    "archived",
]


# --- Routes ---


@app.route("/")
def index():
    return render_template("index.html", statuses=STATUSES)


@app.route("/api/branches")
def api_branches():
    branches = sync_branches()
    known_names = {b["name"] for b in branches}
    # Include pg_init tasks as virtual "creating" entries
    for name, task in pg_init_tasks.items():
        entry = {"name": name, "pg_init_status": task.get("status"),
                 "pg_init_error": task.get("error", "")}
        if name in known_names:
            for b in branches:
                if b["name"] == name:
                    b.update(entry)
                    break
        elif task["status"] == "running":
            entry.update(status="active", exists_on_disk=False, port=None,
                         src_dir=None, pg_running=None, mailing_list_url="",
                         commitfest_url="", notes="", created_at="", updated_at="")
            branches.append(entry)
    return jsonify(branches)


@app.route("/api/branches/<name>", methods=["PUT"])
def api_update_branch(name):
    data = request.get_json()
    db = get_db()

    fields = []
    values = []
    for col in ("status", "mailing_list_url", "commitfest_url", "notes"):
        if col in data:
            fields.append(f"{col} = ?")
            values.append(data[col])

    if not fields:
        return jsonify({"error": "No fields to update"}), 400

    fields.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(name)

    db.execute(
        f"UPDATE branches SET {', '.join(fields)} WHERE name = ?", values
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/branches/<name>", methods=["DELETE"])
def api_delete_branch(name):
    """Remove a branch entry from the database (does not delete worktree)."""
    db = get_db()
    db.execute("DELETE FROM branches WHERE name = ?", (name,))
    db.commit()
    return jsonify({"ok": True})


def _run_pg_init(branch, base_branch):
    """Run pg_init in background thread.

    stdout/stderr are sent to /dev/null so they don't interfere with
    pg_init's own `exec > >(tee ...)` logging.  Passing a pipe or temp
    file from subprocess replaces the fd that tee inherits, which can
    cause SIGPIPE during parallel make and corrupt the build.
    """
    cmd = [str(PG_INIT), "-b", branch, "-B", base_branch]
    try:
        result = subprocess.run(
            cmd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            # Check log file for error details
            error = f"pg_init exited with code {result.returncode}"
            if LOGS_DIR.exists():
                logs = sorted(LOGS_DIR.glob("pg_init_*.log"), reverse=True)
                for f in logs:
                    try:
                        content = f.read_text(errors="replace")
                        if branch in content:
                            error = content
                            break
                    except OSError:
                        continue
            pg_init_tasks[branch] = {"status": "error", "error": error}
        else:
            pg_init_tasks[branch] = {"status": "done"}
    except Exception as e:
        pg_init_tasks[branch] = {"status": "error", "error": str(e)}


@app.route("/api/pg_init", methods=["POST"])
def api_pg_init():
    data = request.get_json()
    branch = data.get("branch", "").strip()
    base_branch = data.get("base_branch", "master").strip()

    if not branch:
        return jsonify({"error": "Branch name is required"}), 400

    if branch in pg_init_tasks and pg_init_tasks[branch]["status"] == "running":
        return jsonify({"error": f"{branch} is already being created"}), 409

    pg_init_tasks[branch] = {"status": "running"}
    thread = threading.Thread(target=_run_pg_init, args=(branch, base_branch), daemon=True)
    thread.start()

    return jsonify({"ok": True, "status": "running"})


@app.route("/api/pg_init/<branch>", methods=["GET"])
def api_pg_init_status(branch):
    task = pg_init_tasks.get(branch)
    if not task:
        return jsonify({"status": "unknown"}), 404
    return jsonify(task)


@app.route("/api/pg_init", methods=["GET"])
def api_pg_init_list():
    """Return all pg_init task statuses."""
    return jsonify(pg_init_tasks)


@app.route("/api/branches/<name>/pg", methods=["POST"])
def api_pg_ctl(name):
    data = request.get_json()
    action = data.get("action")
    if action not in ("start", "stop"):
        return jsonify({"error": "action must be 'start' or 'stop'"}), 400

    ctl = pg_ctl_path(name)
    pgdata = pg_data_path(name)
    if not ctl.exists() or not pgdata.exists():
        return jsonify({"error": f"pg_ctl or data directory not found for {name}"}), 404

    port_map = parse_port_lock()
    port = port_map.get(name)

    if action == "start":
        cmd = [str(ctl), "start", "-D", str(pgdata), "-l", str(pgdata / "server.log")]
        if port:
            cmd += ["-o", f"-p {port}"]
    else:
        cmd = [str(ctl), "stop", "-D", str(pgdata)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return jsonify({"error": output}), 500
        return jsonify({"ok": True, "output": output})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/branches/<name>/pg", methods=["GET"])
def api_pg_status(name):
    status = check_pg_running(name)
    return jsonify({"name": name, "pg_running": status})


def remove_port_lock_entry(name):
    """Remove a branch's entry from the port_lock file."""
    if not PORT_LOCK.exists():
        return
    lines = PORT_LOCK.read_text().splitlines()
    new_lines = [
        line for line in lines
        if not (line.strip().split()[1:2] == [name] if len(line.strip().split()) >= 2 else False)
    ]
    if len(new_lines) != len(lines):
        PORT_LOCK.write_text("\n".join(new_lines) + "\n" if new_lines else "")


@app.route("/api/branches/<name>/archive", methods=["POST"])
def api_archive_branch(name):
    """Archive a branch: stop PG, move to _archive, remove worktree/branches, update DB."""
    project_dir = PGSQL_DIR / name
    if not project_dir.exists():
        return jsonify({"error": f"Directory {name} not found"}), 404

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
            return jsonify({"error": f"Failed to stop PostgreSQL: {result.stdout + result.stderr}"}), 500

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
    db = get_db()
    db.execute(
        "UPDATE branches SET status = 'archived', updated_at = ? WHERE name = ?",
        (datetime.now().isoformat(), name),
    )
    db.commit()
    steps.append("Updated status to archived")

    return jsonify({"ok": True, "steps": steps})


@app.route("/api/logs")
def api_logs_list():
    """List pg_init log files, newest first. Optional ?branch= filter."""
    if not LOGS_DIR.exists():
        return jsonify([])
    logs = sorted(LOGS_DIR.glob("pg_init_*.log"), reverse=True)
    branch = request.args.get("branch")
    result = []
    for f in logs:
        entry = {"name": f.name, "size": f.stat().st_size,
                 "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
        if branch:
            try:
                head = f.read_text(errors="replace")[:4096]
                if branch not in head:
                    continue
            except OSError:
                continue
        result.append(entry)
    return jsonify(result)


@app.route("/api/logs/<name>")
def api_log_content(name):
    """Return content of a specific log file."""
    if "/" in name or "\\" in name or ".." in name:
        return jsonify({"error": "Invalid filename"}), 400
    log_path = LOGS_DIR / name
    if not log_path.exists():
        return jsonify({"error": "Log not found"}), 404
    tail = request.args.get("tail", type=int)
    content = log_path.read_text(errors="replace")
    if tail:
        lines = content.splitlines()
        content = "\n".join(lines[-tail:])
    return jsonify({"name": name, "content": content})


@app.route("/api/statuses")
def api_statuses():
    return jsonify(STATUSES)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=30001, debug=True, threaded=True)
