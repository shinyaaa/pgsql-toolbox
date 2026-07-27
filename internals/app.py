#!/usr/bin/env python3
"""PostgreSQL Documentation Server."""

import os
import re
import subprocess
from pathlib import Path

from flask import Flask, abort, jsonify, make_response, render_template, send_from_directory

app = Flask(__name__, template_folder="templates")

BASE_DIR = Path(__file__).parent
REPO_DIR = Path(__file__).resolve().parent.parent

# Documentation categories shown as tabs on the index page.
# `prefix` is the URL prefix: internals docs keep the historical top-level
# `/<topic>/` URLs, the other categories live under their own prefix.
# Topics named "user" or "patch" are therefore reserved in internals/docs/.
CATEGORIES = [
    {
        "key": "internals",
        "label": "インターナルドキュメント",
        "dir": "docs",
        "prefix": "",
        "hint": "db-internals-docs スキルを使って生成してください。",
    },
    {
        "key": "user",
        "label": "ユーザドキュメント",
        "dir": "user_docs",
        "prefix": "user",
        "hint": "ユーザ向けドキュメントを生成してください。",
    },
    {
        "key": "patch",
        "label": "パッチ解説ドキュメント",
        "dir": "patch_docs",
        "prefix": "patch",
        "hint": "パッチ解説ドキュメントを生成してください。",
    },
]

_VERSION_RE = re.compile(r'<span class="version-badge">(?:PostgreSQL\s+)?([^<]+)</span>')


def _extract_version(index_path):
    try:
        m = _VERSION_RE.search(index_path.read_text(encoding="utf-8"))
        return m.group(1).strip() if m else None
    except OSError:
        return None


def scan_docs(docs_dir):
    """Scan a documentation directory for documentation sets."""
    if not docs_dir.exists():
        return []
    return [
        {"name": d.name, "version": _extract_version(d / "index.html")}
        for d in sorted(docs_dir.iterdir())
        if d.is_dir() and (d / "index.html").exists()
    ]


def scan_categories():
    """Scan every category directory, keeping the tab order of CATEGORIES."""
    result = []
    for cat in CATEGORIES:
        entry = dict(cat)
        entry["base"] = f"/{cat['prefix']}/" if cat["prefix"] else "/"
        entry["path"] = f"internals/{cat['dir']}/<topic>/index.html"
        entry["topics"] = scan_docs(BASE_DIR / cat["dir"])
        result.append(entry)
    return result


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


def _no_store(response):
    """Keep the browser from reusing a cached copy.

    Firefox otherwise serves the index from bfcache when coming Back from a
    doc, so the topic list can be stale right after a successful update.
    """
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/")
def index():
    categories = scan_categories()
    return _no_store(make_response(render_template("index.html", categories=categories)))


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


def _send_index(docs_dir, topic):
    doc_dir = docs_dir / topic
    if not doc_dir.exists() or not (doc_dir / "index.html").exists():
        abort(404)
    return send_from_directory(str(doc_dir), "index.html")


def _send_file(docs_dir, topic, filename):
    doc_dir = docs_dir / topic
    if not doc_dir.exists():
        abort(404)
    return send_from_directory(str(doc_dir), filename)


@app.route("/user/<topic>/")
@app.route("/user/<topic>/index.html")
def user_doc_index(topic):
    return _send_index(BASE_DIR / "user_docs", topic)


@app.route("/user/<topic>/<path:filename>")
def user_doc_file(topic, filename):
    return _send_file(BASE_DIR / "user_docs", topic, filename)


@app.route("/patch/<topic>/")
@app.route("/patch/<topic>/index.html")
def patch_doc_index(topic):
    return _send_index(BASE_DIR / "patch_docs", topic)


@app.route("/patch/<topic>/<path:filename>")
def patch_doc_file(topic, filename):
    return _send_file(BASE_DIR / "patch_docs", topic, filename)


@app.route("/<topic>/")
@app.route("/<topic>/index.html")
def doc_index(topic):
    return _send_index(BASE_DIR / "docs", topic)


@app.route("/<topic>/<path:filename>")
def doc_file(topic, filename):
    return _send_file(BASE_DIR / "docs", topic, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=30002, debug=True)
