#!/usr/bin/env python3
"""PostgreSQL Worktree Dashboard Server."""

import sqlite3
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

from lib.config import DB_PATH, HIDDEN_DIRS, LOG_PREVIEW_SIZE, LOGS_DIR, PGSQL_DIR, standby_port
from lib.db import get_standbys, init_db, remove_standbys
from lib.init import init_branch
from lib.operations import (
    archive_branch,
    check_pg_running,
    parse_port_lock,
    pg_ctl_path,
    pg_data_path,
    remove_port_lock_entry,
    scan_worktrees,
    validate_branch_name,
)
from lib.replication import (
    build_cluster,
    reload_cluster,
    restart_cluster,
    start_cluster,
    stop_cluster,
)

app = Flask(__name__)

# Track background pg_init tasks: branch_name -> {"status": "running"/"done"/"error", "error": "..."}
_pg_init_lock = threading.Lock()
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

    # Load all standby records at once
    standby_rows = db.execute(
        "SELECT primary_name, standby_index, repl_type FROM standbys ORDER BY standby_index"
    ).fetchall()
    standby_map = {}
    for sr in standby_rows:
        standby_map.setdefault(sr["primary_name"], []).append(dict(sr))

    rows = db.execute("SELECT * FROM branches ORDER BY name").fetchall()
    branches = []
    for row in rows:
        if row["name"] in HIDDEN_DIRS:
            continue
        d = dict(row)
        d["port"] = port_map.get(d["name"])
        d["exists_on_disk"] = d["name"] in worktrees
        src_dir = PGSQL_DIR / d["name"] / "postgres"
        d["src_dir"] = str(src_dir) if src_dir.exists() else None
        d["pg_running"] = check_pg_running(d["name"]) if d["exists_on_disk"] else None

        # Attach standby info
        sbs = standby_map.get(d["name"], [])
        for sb in sbs:
            sb["port"] = standby_port(d["port"], sb["standby_index"]) if d["port"] else None
            sb["pg_running"] = check_pg_running(d["name"], sb["standby_index"]) if d["exists_on_disk"] else None
        d["standbys"] = sbs

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
    with _pg_init_lock:
        tasks_snapshot = dict(pg_init_tasks)
    for name, task in tasks_snapshot.items():
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
    db.execute("DELETE FROM standbys WHERE primary_name = ?", (name,))
    db.execute("DELETE FROM branches WHERE name = ?", (name,))
    db.commit()
    return jsonify({"ok": True})


def _run_pg_init(branch, base_branch, standbys=None):
    """Run pg_init in background thread."""
    try:
        init_branch(branch, base_branch, standbys=standbys)
        with _pg_init_lock:
            pg_init_tasks[branch] = {"status": "done"}
    except Exception as e:
        # Try to get details from log files
        error = str(e)
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
        with _pg_init_lock:
            pg_init_tasks[branch] = {"status": "error", "error": error}


@app.route("/api/pg_init", methods=["POST"])
def api_pg_init():
    data = request.get_json()
    standbys = data.get("standbys")  # e.g. [{"type": "streaming_sync"}, ...]

    try:
        branch = validate_branch_name(data.get("branch", ""))
        base_branch = validate_branch_name(data.get("base_branch", "master"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    with _pg_init_lock:
        if branch in pg_init_tasks and pg_init_tasks[branch]["status"] == "running":
            return jsonify({"error": f"{branch} is already being created"}), 409
        pg_init_tasks[branch] = {"status": "running"}

    thread = threading.Thread(
        target=_run_pg_init, args=(branch, base_branch, standbys), daemon=True
    )
    thread.start()

    return jsonify({"ok": True, "status": "running"})


@app.route("/api/pg_init/<branch>", methods=["GET"])
def api_pg_init_status(branch):
    with _pg_init_lock:
        task = pg_init_tasks.get(branch)
    if not task:
        return jsonify({"status": "unknown"}), 404
    return jsonify(task)


@app.route("/api/pg_init", methods=["GET"])
def api_pg_init_list():
    """Return all pg_init task statuses."""
    with _pg_init_lock:
        snapshot = dict(pg_init_tasks)
    return jsonify(snapshot)


@app.route("/api/branches/<name>/pg", methods=["POST"])
def api_pg_ctl(name):
    data = request.get_json()
    action = data.get("action")
    standby_index = data.get("standby_index")  # optional int
    if action not in ("start", "stop"):
        return jsonify({"error": "action must be 'start' or 'stop'"}), 400

    ctl = pg_ctl_path(name)
    pgdata = pg_data_path(name, standby_index)
    if not ctl.exists() or not pgdata.exists():
        return jsonify({"error": f"pg_ctl or data directory not found for {name}"}), 404

    port_map = parse_port_lock()
    port = port_map.get(name)
    if port and standby_index is not None:
        port = standby_port(port, standby_index)

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
    except subprocess.TimeoutExpired:
        return jsonify({"error": "pg_ctl timed out after 30s"}), 500
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/branches/<name>/pg", methods=["GET"])
def api_pg_status(name):
    standby_index = request.args.get("standby_index", type=int)
    status = check_pg_running(name, standby_index)
    return jsonify({"name": name, "pg_running": status})


@app.route("/api/branches/<name>/cluster", methods=["POST"])
def api_cluster_action(name):
    """Cluster-level operations: start, stop, restart, reload, build."""
    data = request.get_json()
    action = data.get("action")
    if action not in ("start", "stop", "restart", "reload", "build"):
        return jsonify({"error": "action must be start/stop/restart/reload/build"}), 400

    port_map = parse_port_lock()
    port = port_map.get(name)
    if not port:
        return jsonify({"error": f"No port found for {name}"}), 404

    project_dir = PGSQL_DIR / name
    if not project_dir.exists():
        return jsonify({"error": f"Directory {name} not found"}), 404

    sbs = get_standbys(name)
    standby_list = [{"standby_index": s["standby_index"], "repl_type": s["repl_type"]} for s in sbs]

    try:
        if action == "start":
            start_cluster(project_dir, name, port, standby_list)
        elif action == "stop":
            stop_cluster(project_dir, name, port, standby_list)
        elif action == "restart":
            restart_cluster(project_dir, name, port, standby_list)
        elif action == "reload":
            reload_cluster(project_dir, name, port, standby_list)
        elif action == "build":
            src_dir = project_dir / "postgres"
            if not src_dir.exists():
                return jsonify({"error": "Source directory not found"}), 404
            build_cluster(src_dir, project_dir, port, standby_list)
        return jsonify({"ok": True, "action": action})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/branches/<name>/archive", methods=["POST"])
def api_archive_branch(name):
    """Archive a branch: stop PG, move to _archive, remove worktree/branches, update DB."""
    try:
        steps = archive_branch(name)
        return jsonify({"ok": True, "steps": steps})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


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
                head = f.read_text(errors="replace")[:LOG_PREVIEW_SIZE]
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
