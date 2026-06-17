#!/usr/bin/env python3
"""PostgreSQL Internals Documentation Server."""

import os
import re
import subprocess
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, send_from_directory

app = Flask(__name__, template_folder="templates")

DOCS_DIR = Path(__file__).parent / "docs"
REPO_DIR = Path(__file__).resolve().parent.parent

_VERSION_RE = re.compile(r'<span class="version-badge">(?:PostgreSQL\s+)?([^<]+)</span>')


def _extract_version(index_path):
    try:
        m = _VERSION_RE.search(index_path.read_text(encoding="utf-8"))
        return m.group(1).strip() if m else None
    except OSError:
        return None


def scan_docs():
    """Scan internals/docs/ for documentation sets."""
    if not DOCS_DIR.exists():
        return []
    return [
        {"name": d.name, "version": _extract_version(d / "index.html")}
        for d in sorted(DOCS_DIR.iterdir())
        if d.is_dir() and (d / "index.html").exists()
    ]


def _git_env():
    """Environment for git over SSH on this host.

    The system-wide /etc/ssh/ssh_config carries invalid client options that make
    the ssh client abort, so force ssh to ignore it with `-F /dev/null` and pass
    our own non-interactive settings (so the button never hangs on a prompt).
    """
    env = os.environ.copy()
    known_hosts = os.path.expanduser("~/.ssh/known_hosts")
    env["GIT_SSH_COMMAND"] = (
        "ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=accept-new "
        f"-o UserKnownHostsFile={known_hosts}"
    )
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


@app.route("/")
def index():
    topics = scan_docs()
    return render_template("index.html", topics=topics)


@app.route("/api/pull", methods=["POST"])
def api_pull():
    """Fast-forward the local repo from origin so newly merged docs appear."""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(REPO_DIR),
            env=_git_env(),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "output": "git pull timed out after 120s"}), 504
    except OSError as e:
        return jsonify({"ok": False, "output": str(e)}), 500

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        return jsonify({"ok": False, "output": output or "git pull failed"}), 500
    return jsonify({"ok": True, "output": output or "Already up to date."})



@app.route("/<topic>/")
@app.route("/<topic>/index.html")
def doc_index(topic):
    doc_dir = DOCS_DIR / topic
    if not doc_dir.exists() or not (doc_dir / "index.html").exists():
        abort(404)
    return send_from_directory(str(doc_dir), "index.html")


@app.route("/<topic>/<path:filename>")
def doc_file(topic, filename):
    doc_dir = DOCS_DIR / topic
    if not doc_dir.exists():
        abort(404)
    return send_from_directory(str(doc_dir), filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=30002, debug=True)
