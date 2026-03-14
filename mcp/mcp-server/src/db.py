"""Async database connection pool and search queries for the MCP server."""

import os
import logging
import re

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger("mcp_server.db")

_pool: AsyncConnectionPool | None = None

# Patterns that indicate an identifier query (use pg_trgm instead of tsvector)
_IDENTIFIER_PATTERNS = [
    re.compile(r"[a-z]_[a-z]"),          # snake_case
    re.compile(r"[A-Z][a-z]+[A-Z]"),     # CamelCase
    re.compile(r"\.\w+$"),               # file extension (.c, .h, .py)
]


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        conninfo = (
            f"host={os.environ.get('POSTGRES_HOST', 'db')} "
            f"port={os.environ.get('POSTGRES_PORT', '5432')} "
            f"dbname={os.environ.get('POSTGRES_DB', 'pgsql_hackers')} "
            f"user={os.environ.get('POSTGRES_USER', 'hackers')} "
            f"password={os.environ.get('POSTGRES_PASSWORD', 'hackers_dev')}"
        )
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=10,
            open=False,
            kwargs={"row_factory": dict_row},
        )
        await _pool.open()
        logger.info("Database connection pool opened")
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def is_identifier_query(query: str) -> bool:
    """Detect if query looks like a code identifier (use pg_trgm)."""
    return any(p.search(query) for p in _IDENTIFIER_PATTERNS)


# ---------------------------------------------------------------------------
# list_name filter helper
# ---------------------------------------------------------------------------

def _list_filter(alias: str = "m") -> str:
    """Return a SQL WHERE clause fragment for list_name filtering.

    When used, the query params must include ``list_name``.
    Returns empty string when list_name is empty/None.
    """
    return f"AND {alias}.list_name = %(list_name)s"


# ---------------------------------------------------------------------------
# tsvector query helper (websearch with plainto fallback)
# ---------------------------------------------------------------------------

async def _execute_tsquery(
    cur,
    sql_template: str,
    params: dict,
) -> list[dict]:
    """Execute a tsvector search query with websearch_to_tsquery, falling back
    to plainto_tsquery on syntax error.

    sql_template must contain {tsquery_func} placeholders that will be replaced
    with the appropriate function name.
    """
    try:
        sql = sql_template.format(tsquery_func="websearch_to_tsquery")
        await cur.execute(sql, params)
    except Exception:
        logger.warning("websearch_to_tsquery failed, falling back to plainto_tsquery")
        sql = sql_template.format(tsquery_func="plainto_tsquery")
        await cur.execute(sql, params)
    return await cur.fetchall()


# ---------------------------------------------------------------------------
# list_mailing_lists
# ---------------------------------------------------------------------------


async def get_mailing_lists() -> list[dict]:
    """Return all mailing lists with message counts."""
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    list_name,
                    count(*) AS message_count,
                    min(sent_at) AS first_message,
                    max(sent_at) AS last_message
                FROM messages
                GROUP BY list_name
                ORDER BY message_count DESC
                """
            )
            return await cur.fetchall()


# ---------------------------------------------------------------------------
# search_messages (tsvector / trigram)
# ---------------------------------------------------------------------------

_AUTHOR_WHERE = """(
        EXISTS (
            SELECT 1 FROM authors a
            JOIN author_emails ae ON ae.author_id = a.author_id
            WHERE a.author_id = m.author_id
              AND (a.display_name ILIKE '%%' || %(author)s || '%%'
                   OR ae.email ILIKE '%%' || %(author)s || '%%')
        )
        OR (m.author_id IS NULL AND m.sender ILIKE '%%' || %(author)s || '%%')
    )"""

_TSVECTOR_SEARCH_SQL = """
    SELECT
        m.message_id,
        m.list_name,
        m.subject,
        m.sender,
        m.sent_at,
        m.thread_id,
        t.status AS thread_status,
        ts_rank_cd(m.body_tsv, {{tsquery_func}}('english', %(q)s)) AS rank,
        ts_headline('english', m.body,
            {{tsquery_func}}('english', %(q)s),
            'MaxWords=60, MinWords=20, MaxFragments=3'
        ) AS snippet
    FROM messages m
    LEFT JOIN threads t ON m.thread_id = t.thread_id
    WHERE m.body_tsv @@ {{tsquery_func}}('english', %(q)s)
      {author_filter}
      {list_filter}
    ORDER BY rank DESC, m.sent_at DESC
    LIMIT %(limit)s OFFSET %(offset)s
"""


async def search_messages_tsvector(
    query: str,
    limit: int = 20,
    offset: int = 0,
    list_name: str = "",
    author: str = "",
) -> list[dict]:
    """Full-text search using tsvector + websearch_to_tsquery."""
    lf = _list_filter() if list_name else ""
    af = f"AND {_AUTHOR_WHERE}" if author else ""
    sql = _TSVECTOR_SEARCH_SQL.format(list_filter=lf, author_filter=af)
    params: dict = {"q": query, "limit": limit, "offset": offset}
    if list_name:
        params["list_name"] = list_name
    if author:
        params["author"] = author
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            return await _execute_tsquery(cur, sql, params)


async def search_messages_trigram(
    query: str,
    limit: int = 20,
    offset: int = 0,
    list_name: str = "",
    author: str = "",
) -> list[dict]:
    """Substring search using pg_trgm for identifiers."""
    lf = _list_filter() if list_name else ""
    af = f"AND {_AUTHOR_WHERE}" if author else ""
    params: dict = {"q": query, "limit": limit, "offset": offset}
    if list_name:
        params["list_name"] = list_name
    if author:
        params["author"] = author
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                SELECT
                    m.message_id,
                    m.list_name,
                    m.subject,
                    m.sender,
                    m.sent_at,
                    m.thread_id,
                    t.status AS thread_status,
                    similarity(m.body, %(q)s) AS rank,
                    substring(m.body FROM greatest(1, position(lower(%(q)s) in lower(m.body)) - 100)
                              FOR 200 + length(%(q)s)) AS snippet
                FROM messages m
                LEFT JOIN threads t ON m.thread_id = t.thread_id
                WHERE m.body ILIKE '%%' || %(q)s || '%%'
                  {af}
                  {lf}
                ORDER BY rank DESC, m.sent_at DESC
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                params,
            )
            return await cur.fetchall()


# ---------------------------------------------------------------------------
# get_message
# ---------------------------------------------------------------------------


async def get_message_by_id(message_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    m.message_id,
                    m.list_name,
                    m.thread_id,
                    m.parent_id,
                    m.subject,
                    m.sender,
                    m.sent_at,
                    m.body,
                    t.subject AS thread_subject,
                    t.status AS thread_status,
                    (SELECT count(*) FROM patches p
                     WHERE p.message_id = m.message_id) AS patch_count
                FROM messages m
                LEFT JOIN threads t ON m.thread_id = t.thread_id
                WHERE m.message_id = %(mid)s
                """,
                {"mid": message_id},
            )
            return await cur.fetchone()


# ---------------------------------------------------------------------------
# get_thread
# ---------------------------------------------------------------------------


async def get_thread_info(thread_id: str) -> dict | None:
    """Get thread metadata including message count."""
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    t.thread_id,
                    t.subject,
                    t.status,
                    t.list_names,
                    t.started_at,
                    t.ended_at,
                    (SELECT count(*) FROM messages m
                     WHERE m.thread_id = t.thread_id) AS message_count
                FROM threads t
                WHERE t.thread_id = %(tid)s
                """,
                {"tid": thread_id},
            )
            return await cur.fetchone()


async def get_thread_messages(thread_id: str) -> list[dict]:
    """Get all messages in a thread chronologically."""
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    m.message_id,
                    m.list_name,
                    m.parent_id,
                    m.subject,
                    m.sender,
                    m.sent_at,
                    m.body,
                    length(m.body) AS body_length,
                    (SELECT count(*) FROM patches p
                     WHERE p.message_id = m.message_id) AS patch_count
                FROM messages m
                WHERE m.thread_id = %(tid)s
                ORDER BY m.sent_at ASC
                """,
                {"tid": thread_id},
            )
            return await cur.fetchall()


# ---------------------------------------------------------------------------
# search_patches / get_patch
# ---------------------------------------------------------------------------


async def search_patches_query(
    query: str,
    limit: int = 10,
    offset: int = 0,
    list_name: str = "",
) -> list[dict]:
    """Search patches by file path or diff content."""
    lf = _list_filter() if list_name else ""
    params: dict = {"q": query, "limit": limit, "offset": offset}
    if list_name:
        params["list_name"] = list_name
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""
                SELECT
                    p.patch_id,
                    p.message_id,
                    m.list_name,
                    p.filename,
                    p.files_changed,
                    m.subject,
                    m.sender,
                    m.sent_at,
                    substring(p.raw_diff FROM 1 FOR 500) AS diff_preview
                FROM patches p
                JOIN messages m ON p.message_id = m.message_id
                WHERE (
                    EXISTS (
                        SELECT 1 FROM unnest(p.files_changed) f
                        WHERE f ILIKE '%%' || %(q)s || '%%'
                    )
                    OR p.filename ILIKE '%%' || %(q)s || '%%'
                    OR p.raw_diff ILIKE '%%' || %(q)s || '%%'
                )
                  {lf}
                ORDER BY m.sent_at DESC
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                params,
            )
            return await cur.fetchall()


async def get_patch_by_id(patch_id: int) -> dict | None:
    """Get a specific patch by its ID."""
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    p.patch_id,
                    p.message_id,
                    m.list_name,
                    p.filename,
                    p.content_type,
                    p.files_changed,
                    p.raw_diff,
                    m.subject,
                    m.sender,
                    m.sent_at
                FROM patches p
                JOIN messages m ON p.message_id = m.message_id
                WHERE p.patch_id = %(pid)s
                """,
                {"pid": patch_id},
            )
            return await cur.fetchone()


