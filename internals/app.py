#!/usr/bin/env python3
"""PostgreSQL Documentation Server."""

import os
import re
import subprocess
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, send_from_directory

app = Flask(__name__, template_folder="templates")

BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent

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

# Repo-relative doc directories, used when only the docs can be updated.
DOC_DIRS = [str((BASE_DIR / cat["dir"]).relative_to(REPO_DIR)) for cat in CATEGORIES]

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


def _git(args, timeout=60):
    """Run git in the repo and return (returncode, combined output)."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(REPO_DIR),
        env=_git_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def _git_lines(args):
    rc, out = _git(args)
    return out.splitlines() if rc == 0 else []


def _target_ref():
    """Remote ref that carries the newest docs.

    The upstream of the checked-out branch when there is one, otherwise the
    default branch of origin: the docs server often sits on a feature branch
    or a detached HEAD, while docs are merged into the default branch.
    """
    rc, out = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if rc == 0 and out:
        return out
    rc, out = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    if rc == 0 and out:
        return out
    for ref in ("origin/main", "origin/master"):
        rc, _ = _git(["rev-parse", "--verify", "--quiet", ref])
        if rc == 0:
            return ref
    return None


def _is_ancestor(a, b):
    rc, _ = _git(["merge-base", "--is-ancestor", a, b])
    return rc == 0


def _dirty_paths():
    """Paths git reports as staged, modified or untracked."""
    rc, out = _git(["status", "--porcelain", "--untracked-files=all"])
    if rc != 0:
        return set()
    paths = set()
    for line in out.splitlines():
        entry = line[3:]
        # Renames are reported as "old -> new"; both sides count as dirty.
        for path in entry.split(" -> "):
            paths.add(path.strip().strip('"'))
    return paths


def _matches_ref(path, ref):
    """True when the working-tree file is byte-identical to the one in ref."""
    rc, local = _git(["hash-object", "--", path])
    if rc != 0:
        return False
    rc, remote = _git(["rev-parse", f"{ref}:{path}"])
    return rc == 0 and local == remote


def _incoming_docs(target):
    return set(_git_lines(["diff", "--name-only", "HEAD", target, "--", *DOC_DIRS]))


def _drop_redundant_local_docs(target):
    """Clear local doc files the incoming commits would deliver unchanged.

    Docs are generated in this checkout first and merged upstream afterwards,
    so the leftover local copies carry no information -- but git still refuses
    to fast-forward over them ("untracked working tree files would be
    overwritten by merge"). Dropping the byte-identical ones lets the merge
    run; anything that genuinely differs is left alone.
    """
    for path in sorted(_incoming_docs(target) & _dirty_paths()):
        if not _matches_ref(path, target):
            continue
        rc, _ = _git(["ls-files", "--error-unmatch", "--", path])
        if rc == 0:
            _git(["checkout", "HEAD", "--", path])  # tracked: back to committed content
        else:
            try:
                (REPO_DIR / path).unlink()
            except OSError:
                pass


def _sync_docs(target):
    """Copy the doc trees of `target` into the working tree, without moving HEAD.

    Fallback for checkouts that cannot be fast-forwarded at all -- a branch
    that has diverged from origin, or local changes outside the docs. Only
    files that the local repo has neither committed nor modified are updated,
    so nothing local is lost, and the index is left untouched so the refreshed
    files never sneak into someone's next commit.
    """
    incoming = _incoming_docs(target)
    if not incoming:
        return False, f"Already up to date. (docs match {target})"

    rc, base = _git(["merge-base", "HEAD", target])
    local_edits = set(_git_lines(["diff", "--name-only", base, "HEAD", "--", *DOC_DIRS])) if rc == 0 else set()
    blocked = incoming & (local_edits | _dirty_paths())
    updatable = sorted(incoming - blocked)
    if not updatable:
        return False, f"ローカルの変更があるため更新できません ({len(blocked)} ファイル)"

    for i in range(0, len(updatable), 100):
        chunk = updatable[i:i + 100]
        rc, out = _git(["checkout", target, "--", *chunk])
        if rc != 0:
            return False, out or "ドキュメントの更新に失敗しました"
        _git(["reset", "--quiet", "HEAD", "--", *chunk])

    message = f"{len(updatable)} ファイルを {target} から更新しました (HEAD は移動していません)"
    if blocked:
        message += f" / ローカル変更のためスキップ: {len(blocked)} ファイル"
    return True, message


@app.route("/")
def index():
    categories = scan_categories()
    return render_template("index.html", categories=categories)


@app.route("/api/pull", methods=["POST"])
def api_pull():
    """Update the docs in the working tree from origin.

    A plain `git pull --ff-only` refuses whenever the checkout is not a clean
    fast-forward: a branch that diverged from origin, a feature branch or a
    detached HEAD left checked out, or doc files generated here before being
    merged upstream. The fetched commits are still available in those cases,
    so fall back to refreshing the doc directories instead of giving up.
    """
    try:
        rc, out = _git(["fetch", "--prune", "origin"], timeout=120)
        if rc != 0:
            return jsonify({"ok": False, "changed": False, "output": out or "git fetch failed"}), 500

        target = _target_ref()
        if target is None:
            return jsonify({"ok": False, "changed": False, "output": "origin の追跡ブランチが見つかりません"}), 500

        if _is_ancestor(target, "HEAD"):
            return jsonify({"ok": True, "changed": False, "output": f"Already up to date. ({target})"})

        if _is_ancestor("HEAD", target):
            _drop_redundant_local_docs(target)
            rc, merge_out = _git(["merge", "--ff-only", target], timeout=120)
            if rc == 0:
                return jsonify({"ok": True, "changed": True, "output": merge_out or f"Fast-forwarded to {target}."})

        changed, message = _sync_docs(target)
        return jsonify({"ok": True, "changed": changed, "output": message})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "changed": False, "output": "git がタイムアウトしました"}), 504
    except OSError as e:
        return jsonify({"ok": False, "changed": False, "output": str(e)}), 500


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
