#!/usr/bin/env python3
"""PostgreSQL Internals Documentation Server."""

import re
from pathlib import Path

from flask import Flask, abort, render_template, send_from_directory

app = Flask(__name__, template_folder="templates")

DOCS_DIR = Path(__file__).parent / "docs"

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


@app.route("/")
def index():
    topics = scan_docs()
    return render_template("index.html", topics=topics)



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
