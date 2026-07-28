#!/usr/bin/env python3
"""PostgreSQL Documentation Server."""

import os
import re
import subprocess
from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    make_response,
    render_template,
    request,
    send_from_directory,
)

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
    # Force C locale so the porcelain output we parse never gets translated.
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _git(*args, timeout=30):
    """Run a git command in the repo; return (returncode, combined output)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_DIR),
            env=_git_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"git {' '.join(args)} timed out after {timeout}s"
    except OSError as e:
        return 1, str(e)
    return result.returncode, (result.stdout + result.stderr).strip()


def _current_branch():
    """Current branch name, or None when HEAD is detached."""
    rc, out = _git("symbolic-ref", "--quiet", "--short", "HEAD")
    return out if rc == 0 and out else None


def _upstream():
    """Upstream ref of the current branch, or None when it has no tracking."""
    rc, out = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    return out if rc == 0 and out else None


def _ahead_behind(upstream):
    """(ahead, behind) commit counts of HEAD relative to upstream."""
    rc, out = _git("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
    if rc != 0:
        return None
    try:
        ahead, behind = out.split()
        return int(ahead), int(behind)
    except ValueError:
        return None


def _default_branch():
    """Remote default branch (e.g. "master"), or None when origin/HEAD is unset."""
    rc, out = _git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    return out.split("/", 1)[1] if rc == 0 and "/" in out else None


_BLOCKED_RE = re.compile(
    r"^(?:error: )?Your local changes to the following files would be overwritten"
    r" by merge:\n((?:\t.*\n?)+)",
    re.M,
)


def _blocking_paths(merge_output):
    """Paths git refused to overwrite, from a failed `merge --ff-only`."""
    m = _BLOCKED_RE.search(merge_output + "\n")
    if not m:
        return []
    return [line.strip() for line in m.group(1).splitlines() if line.strip()]


def _pull_ff():
    """Fetch origin and fast-forward the current branch onto its upstream.

    Returns a payload describing what happened. Never rewrites or discards
    anything local: when the branch cannot be fast-forwarded — diverged
    history, conflicting local edits, no tracking branch, detached HEAD — it
    reports which of those it is instead of failing with a bare git error.
    """
    branch = _current_branch()
    if not branch:
        return {
            "ok": False,
            "message": "HEAD が detached です。ブランチをチェックアウトしてください。",
            "detail": "",
        }

    rc, fetch_out = _git("fetch", "--prune", "origin", timeout=120)
    if rc != 0:
        return {
            "ok": False,
            "message": "git fetch に失敗しました",
            "detail": fetch_out,
            "branch": branch,
        }

    upstream = _upstream()
    if not upstream:
        return {
            "ok": False,
            "message": f"{branch} に追跡ブランチがありません",
            "detail": f"git branch --set-upstream-to=origin/{branch} {branch}",
            "branch": branch,
        }

    counts = _ahead_behind(upstream)
    if counts is None:
        return {
            "ok": False,
            "message": f"{upstream} との差分を取得できませんでした",
            "detail": fetch_out,
            "branch": branch,
            "upstream": upstream,
        }
    ahead, behind = counts
    base = {"branch": branch, "upstream": upstream, "ahead": ahead, "behind": behind}

    if behind == 0:
        notes = []
        if ahead:
            notes.append(f"ローカルが {ahead} コミット先行")
        default = _default_branch()
        # Worth saying out loud: docs merged into the default branch never show
        # up while the checkout sits on some other branch.
        if default and branch != default:
            notes.append(f"{branch} を表示中")
        message = "最新です" + (f" ({' / '.join(notes)})" if notes else "")
        return {"ok": True, "updated": False, "message": message, "detail": fetch_out, **base}

    if ahead:
        return {
            "ok": False,
            "message": f"{branch} が {upstream} と分岐しています "
                       f"(ローカル {ahead} / リモート {behind})。手動で解決してください。",
            "detail": fetch_out,
            **base,
        }

    rc, merge_out = _git("merge", "--ff-only", upstream, timeout=120)
    if rc != 0:
        blocked = _blocking_paths(merge_out)
        message = "fast-forward できませんでした"
        if blocked:
            message = (
                f"ローカルの変更が競合しています: {', '.join(blocked)}。"
                "commit または stash してください。"
            )
        return {"ok": False, "message": message, "detail": merge_out, **base}

    return {
        "ok": True,
        "updated": True,
        "message": f"{behind} コミット分更新しました",
        "detail": merge_out,
        **base,
    }


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
    payload = _pull_ff()
    payload.setdefault("updated", False)
    return _no_store(jsonify(payload)), (200 if payload["ok"] else 409)


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
