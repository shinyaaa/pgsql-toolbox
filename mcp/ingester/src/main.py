"""Ingester entry point: discover mbox files, parse, resolve threads, insert into DB."""

import glob
import logging
import os
import re
import sys
import time

import psycopg

from .db import (
    classify_threads,
    ensure_schema,
    get_ingested_files,
    insert_batch,
    record_ingestion,
)
from .mbox_parser import parse_mbox
from .thread_resolver import resolve_threads

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("ingester")


def get_db_connection(max_retries: int = 10, retry_delay: float = 3.0):
    conninfo = psycopg.conninfo.make_conninfo(
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "pgsql_hackers"),
        user=os.environ.get("POSTGRES_USER", "hackers"),
        password=os.environ.get("POSTGRES_PASSWORD", "hackers_dev"),
    )
    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg.connect(conninfo)
            logger.info("Connected to PostgreSQL (attempt %d)", attempt)
            return conn
        except psycopg.OperationalError:
            if attempt == max_retries:
                raise
            logger.warning(
                "DB not ready, retry in %.1fs (attempt %d/%d)",
                retry_delay,
                attempt,
                max_retries,
            )
            time.sleep(retry_delay)


_MBOX_FILENAME_RE = re.compile(r"^(.+)\.(\d{6})$")


def _discover_mbox_files(mbox_dir: str) -> list[tuple[str, str]]:
    """Discover mbox files and extract list names from filenames.

    Returns list of (filepath, list_name) tuples.
    Matches filenames like ``pgsql-hackers.202601``, ``pgsql-general.202601``.
    """
    results = []
    for path in sorted(glob.glob(os.path.join(mbox_dir, "**", "*"), recursive=True)):
        basename = os.path.basename(path)
        m = _MBOX_FILENAME_RE.match(basename)
        if m and os.path.isfile(path):
            results.append((path, m.group(1)))
    return results


def main():
    conn = get_db_connection()
    ensure_schema(conn)
    mbox_dir = os.environ.get("MBOX_DIR", "/data/mbox")

    discovered = _discover_mbox_files(mbox_dir)

    if not discovered:
        logger.warning("No mbox files found in %s", mbox_dir)
        conn.close()
        return

    already_ingested = get_ingested_files(conn)
    pending = []
    for path, list_name in discovered:
        basename = os.path.basename(path)
        mtime = os.path.getmtime(path)
        prev_mtime = already_ingested.get(basename, "missing")
        if prev_mtime == "missing":
            pending.append((path, list_name, mtime))
        elif prev_mtime is None or mtime > prev_mtime + 1.0:
            # Re-process if file was updated (1s tolerance for FS precision)
            pending.append((path, list_name, mtime))

    logger.info(
        "Found %d mbox files, %d already ingested, %d to (re)process",
        len(discovered),
        len(already_ingested),
        len(pending),
    )

    total_messages = 0
    for mbox_path, list_name, mtime in pending:
        basename = os.path.basename(mbox_path)
        logger.info("Processing %s (list: %s) ...", basename, list_name)

        messages = parse_mbox(mbox_path)
        logger.info("  Parsed %d messages from %s", len(messages), basename)

        if not messages:
            record_ingestion(conn, basename, 0, mtime)
            continue

        resolve_threads(messages)
        count, affected_threads = insert_batch(conn, messages, list_name=list_name)
        record_ingestion(conn, basename, count, mtime)
        total_messages += count
        logger.info("  Inserted %d new messages from %s", count, basename)

        if affected_threads:
            stats = classify_threads(conn, affected_threads)
            logger.info("  Classified %d threads: %s", len(affected_threads), stats)

    logger.info("Ingestion complete. Total new messages: %d", total_messages)
    conn.close()


if __name__ == "__main__":
    main()
