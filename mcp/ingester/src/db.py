"""Database operations for the ingester: upsert threads, messages, patches."""

import logging
from email.utils import parseaddr

import psycopg

from .thread_classifier import classify_thread

logger = logging.getLogger("ingester.db")


def _strip_nul(value):
    """Strip NUL bytes from strings (PostgreSQL TEXT cannot store them)."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


def get_ingested_files(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT mbox_file FROM ingestion_log")
        return {row[0] for row in cur.fetchall()}


def record_ingestion(conn: psycopg.Connection, mbox_file: str, count: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ingestion_log (mbox_file, message_count)
               VALUES (%s, %s)
               ON CONFLICT (mbox_file) DO UPDATE SET
                   message_count = EXCLUDED.message_count,
                   ingested_at = now()""",
            (mbox_file, count),
        )
    conn.commit()


def _resolve_or_create_author(cur, display_name: str, email_addr: str) -> int | None:
    """Look up author by email, or create a new one. Returns author_id.

    Returns None if display_name is empty after normalization.
    Must be called within an existing transaction (does not commit).
    """
    cur.execute(
        "SELECT author_id FROM author_emails WHERE email = %s",
        (email_addr,),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    import re
    normalized = re.sub(r'\(.*\)$', '', display_name).strip()
    if not normalized:
        return None

    cur.execute(
        "INSERT INTO authors (display_name) VALUES (%s) RETURNING author_id",
        (normalized,),
    )
    author_id = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO author_emails (email, author_id) VALUES (%s, %s)",
        (email_addr, author_id),
    )
    return author_id


def insert_batch(
    conn: psycopg.Connection,
    messages: list[dict],
    *,
    list_name: str = "pgsql-hackers",
) -> tuple[int, set[str]]:
    """Insert a batch of messages with threads and patches.

    Uses ON CONFLICT DO NOTHING for idempotent re-runs.
    Returns (count of newly inserted messages, set of affected thread_ids).
    """
    inserted = 0

    with conn.transaction():
        with conn.cursor() as cur:
            # Local cache to avoid repeated DB lookups within the batch
            email_to_author: dict[str, int] = {}

            # 1. Upsert threads (with date range from batch messages)
            # Pre-compute per-thread date ranges from this batch
            thread_dates: dict[str, tuple] = {}  # tid -> (min_sent, max_sent)
            for msg in messages:
                tid = msg["thread_id"]
                sent = msg["sent_at"]
                if sent is None:
                    continue
                if tid not in thread_dates:
                    thread_dates[tid] = (sent, sent)
                else:
                    cur_min, cur_max = thread_dates[tid]
                    thread_dates[tid] = (
                        min(cur_min, sent),
                        max(cur_max, sent),
                    )

            threads_seen: set[str] = set()
            for msg in messages:
                tid = msg["thread_id"]
                if tid not in threads_seen:
                    min_sent, max_sent = thread_dates.get(tid, (None, None))
                    cur.execute(
                        """INSERT INTO threads (thread_id, subject, started_at, ended_at, list_names)
                           VALUES (%s, %s, %s, %s, ARRAY[%s])
                           ON CONFLICT (thread_id) DO UPDATE SET
                               started_at = LEAST(threads.started_at, EXCLUDED.started_at),
                               ended_at = GREATEST(threads.ended_at, EXCLUDED.ended_at),
                               list_names = (
                                   SELECT array_agg(DISTINCT x ORDER BY x)
                                   FROM unnest(threads.list_names || EXCLUDED.list_names) AS x
                               )""",
                        (tid, _strip_nul(msg["thread_subject"]), min_sent, max_sent, list_name),
                    )
                    threads_seen.add(tid)

            # 2. Insert messages
            for msg in messages:
                try:
                    # Resolve or create author
                    display_name, email_addr = parseaddr(msg["sender"])
                    if email_addr in email_to_author:
                        author_id = email_to_author[email_addr]
                    else:
                        author_id = _resolve_or_create_author(
                            cur, display_name, email_addr
                        )
                        email_to_author[email_addr] = author_id

                    cur.execute(
                        """INSERT INTO messages
                           (message_id, list_name, thread_id, parent_id, sender,
                            author_id, sent_at, subject, body, body_raw)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (message_id) DO NOTHING""",
                        (
                            msg["message_id"],
                            list_name,
                            msg["thread_id"],
                            msg["parent_id"],
                            _strip_nul(msg["sender"]),
                            author_id,
                            msg["sent_at"],
                            _strip_nul(msg["subject"]),
                            _strip_nul(msg["body"]),
                            _strip_nul(msg["body_raw"]),
                        ),
                    )
                    if cur.rowcount > 0:
                        inserted += 1

                        # 3. Insert patches for newly inserted messages
                        for patch in msg.get("patches", []):
                            cur.execute(
                                """INSERT INTO patches
                                   (message_id, filename, content_type,
                                    files_changed, raw_diff)
                                   VALUES (%s, %s, %s, %s, %s)""",
                                (
                                    msg["message_id"],
                                    patch["filename"],
                                    patch["content_type"],
                                    patch["files_changed"],
                                    _strip_nul(patch["raw_diff"]),
                                ),
                            )
                except Exception:
                    logger.exception("Error inserting message %s", msg["message_id"])

    return inserted, threads_seen


def classify_threads(conn: psycopg.Connection, thread_ids: set[str]) -> dict[str, int]:
    """Classify the status of the given threads using heuristics.

    Queries message bodies and patch counts from the DB, runs the classifier,
    and updates the threads table.

    Returns a dict of {status: count} with the classification results.
    """
    if not thread_ids:
        return {}

    stats: dict[str, int] = {}

    with conn.cursor() as cur:
        for tid in thread_ids:
            # Get message bodies in chronological order
            cur.execute(
                """SELECT COALESCE(body, '') AS body
                   FROM messages
                   WHERE thread_id = %s
                   ORDER BY sent_at ASC NULLS FIRST""",
                (tid,),
            )
            bodies = [row[0] for row in cur.fetchall()]

            # Check if thread has patches
            cur.execute(
                """SELECT EXISTS(
                       SELECT 1 FROM patches p
                       JOIN messages m ON p.message_id = m.message_id
                       WHERE m.thread_id = %s
                   )""",
                (tid,),
            )
            has_patches = cur.fetchone()[0]

            status = classify_thread(bodies, has_patches)

            cur.execute(
                "UPDATE threads SET status = %s WHERE thread_id = %s",
                (status, tid),
            )
            stats[status] = stats.get(status, 0) + 1

    conn.commit()
    return stats
