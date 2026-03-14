"""MCP server for searching PostgreSQL mailing list archives."""

import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from .db import (
    get_mailing_lists,
    get_message_by_id,
    get_patch_by_id,
    get_thread_info,
    get_thread_messages,
    is_identifier_query,
    search_messages_trigram,
    search_messages_tsvector,
    search_patches_query,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_server")

mcp = FastMCP(
    name="pgsql-ml-mcp",
    stateless_http=True,
    json_response=True,
)


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------

def _format_date(sent_at) -> str | None:
    return sent_at.isoformat() if sent_at else None


def _format_search_result(r: dict) -> dict:
    """Format a DB search result row into a message search result."""
    return {
        "message_id": r["message_id"],
        "list_name": r["list_name"],
        "subject": r["subject"],
        "sender": r["sender"],
        "date": _format_date(r["sent_at"]),
        "thread_id": r["thread_id"],
        "thread_status": r.get("thread_status"),
        "relevance": round(float(r["rank"]), 4),
        "snippet": r["snippet"],
    }


def _clamp_pagination(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(50, limit)), max(0, offset)


# ---------------------------------------------------------------------------
# Tool: list_mailing_lists
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_mailing_lists() -> str:
    """List all PostgreSQL mailing lists available in the archive.

    Returns the name of each mailing list along with its message count
    and date range. Use the list_name value to filter searches.

    Common PostgreSQL mailing lists:
    - pgsql-hackers: Core development discussions
    - pgsql-bugs: Bug reports
    - pgsql-committers: Commit notifications
    - pgsql-docs: Documentation discussions
    """
    lists = await get_mailing_lists()

    if not lists:
        return json.dumps(
            {
                "total": 0,
                "lists": [],
                "hint": "No mailing lists found. Run the ingester to import mbox archives.",
            }
        )

    return json.dumps(
        {
            "total": len(lists),
            "lists": [
                {
                    "list_name": r["list_name"],
                    "message_count": r["message_count"],
                    "first_message": _format_date(r["first_message"]),
                    "last_message": _format_date(r["last_message"]),
                }
                for r in lists
            ],
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# Tool: search_messages
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_messages(
    query: str,
    list_name: str = "",
    author: str = "",
    limit: int = 10,
    offset: int = 0,
) -> str:
    """Search the PostgreSQL mailing list archive for messages matching a query.

    Use this tool to find discussions, decisions, patch reviews, and technical
    debates on PostgreSQL mailing lists (pgsql-hackers, pgsql-bugs, pgsql-committers, etc.).

    The search automatically detects the query type:
    - Natural language queries use full-text search with websearch syntax:
      "vacuum freeze", "vacuum OR autovacuum", "-autovacuum vacuum"
    - Code identifiers (snake_case, CamelCase, file paths like nbtinsert.c)
      use substring matching for partial hits.

    Examples:
    - "vacuum freeze" → full-text search for discussions about vacuum freeze
    - "heapam_tuple_insert" → substring match finding all mentions
    - "ExecInitNode" → substring match for CamelCase identifiers
    - author="Tom Lane", query="vacuum" → Tom Lane's messages about vacuum

    Returns a list of matching messages with: message_id, list_name, subject,
    sender, date, thread_id, relevance rank, and a text snippet showing match
    context.

    Use the message_id from results with get_message to retrieve the full body.

    Args:
        query: Search query. Natural language or code identifier.
        list_name: Filter by mailing list (e.g. "pgsql-hackers"). Empty = all lists.
        author: Filter by author name or email (partial match, case-insensitive). Empty = all authors.
        limit: Maximum number of results to return (1-50, default 10).
        offset: Number of results to skip for pagination (default 0).
    """
    limit, offset = _clamp_pagination(limit, offset)

    use_trigram = is_identifier_query(query)

    if use_trigram:
        results = await search_messages_trigram(
            query, limit=limit, offset=offset, list_name=list_name, author=author
        )
        search_mode = "trigram"
    else:
        results = await search_messages_tsvector(
            query, limit=limit, offset=offset, list_name=list_name, author=author
        )
        search_mode = "tsvector"

    if not results:
        return json.dumps(
            {
                "total_results": 0,
                "search_mode": search_mode,
                "messages": [],
                "hint": "No results found. Try broader search terms or different keywords.",
            }
        )

    return json.dumps(
        {
            "total_results": len(results),
            "search_mode": search_mode,
            "messages": [_format_search_result(r) for r in results],
            "hint": "Use get_message with a message_id to read the full message body.",
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# Tool: get_message
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_message(message_id: str) -> str:
    """Retrieve a specific message from the PostgreSQL mailing list archive.

    Use this tool after search_messages to read the full body of a message.
    The message_id comes from search results.

    Returns the complete message including: full body text, sender, date,
    subject, thread information, and whether patches are attached.

    Args:
        message_id: The unique Message-ID of the email to retrieve.
    """
    msg = await get_message_by_id(message_id)

    if msg is None:
        return json.dumps(
            {
                "error": f"Message not found: {message_id}",
                "hint": "Double-check the message_id from search results.",
            }
        )

    body = msg["body"] or ""

    MAX_BODY_LENGTH = 12000
    truncated = False
    if len(body) > MAX_BODY_LENGTH:
        body = body[:MAX_BODY_LENGTH]
        truncated = True

    result = {
        "message_id": msg["message_id"],
        "list_name": msg["list_name"],
        "thread_id": msg["thread_id"],
        "parent_id": msg["parent_id"],
        "subject": msg["subject"],
        "sender": msg["sender"],
        "date": _format_date(msg["sent_at"]),
        "thread_subject": msg["thread_subject"],
        "thread_status": msg.get("thread_status"),
        "body": body,
        "body_truncated": truncated,
        "patch_count": msg["patch_count"],
    }

    hints = []
    if msg["patch_count"] > 0:
        hints.append(
            f"This message has {msg['patch_count']} patch(es). "
            "Use search_patches with the message subject or file path to find them."
        )
    if msg["thread_id"]:
        hints.append(
            "Use get_thread with the thread_id to see the full discussion."
        )
    if hints:
        result["hint"] = " ".join(hints)

    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Tool: get_thread
# ---------------------------------------------------------------------------

# Context window budget for get_thread (characters)
_THREAD_BUDGET = 30000
_BODY_MIN = 200      # minimum body preview per message
_BODY_RECENT = 2000  # body budget for the most recent messages


@mcp.tool()
async def get_thread(thread_id: str) -> str:
    """Retrieve all messages in a thread from the PostgreSQL mailing list archive.

    Returns the thread subject and all messages in chronological order.
    Message bodies are automatically truncated to fit the context window:
    recent messages get more text, older messages get shorter previews.

    Use get_message to read the full body of any individual message.

    Args:
        thread_id: The thread ID (root message's Message-ID) from search results.
    """
    info = await get_thread_info(thread_id)
    if info is None:
        return json.dumps(
            {
                "error": f"Thread not found: {thread_id}",
                "hint": "Double-check the thread_id from search results.",
            }
        )

    messages = await get_thread_messages(thread_id)
    if not messages:
        return json.dumps(
            {
                "thread_id": info["thread_id"],
                "subject": info["subject"],
                "status": info["status"],
                "list_names": info["list_names"],
                "started_at": _format_date(info["started_at"]),
                "ended_at": _format_date(info["ended_at"]),
                "message_count": 0,
                "messages": [],
            }
        )

    # Context window management: allocate body budget
    total = len(messages)
    # Recent 20% of messages (at least 3) get more body text
    recent_count = max(3, total // 5)

    formatted = []
    for idx, m in enumerate(messages):
        body = m["body"] or ""
        is_recent = idx >= total - recent_count

        if is_recent:
            max_len = _BODY_RECENT
        else:
            max_len = _BODY_MIN

        body_truncated = len(body) > max_len
        if body_truncated:
            body = body[:max_len]

        formatted.append(
            {
                "message_id": m["message_id"],
                "list_name": m["list_name"],
                "parent_id": m["parent_id"],
                "subject": m["subject"],
                "sender": m["sender"],
                "date": _format_date(m["sent_at"]),
                "body": body,
                "body_truncated": body_truncated,
                "body_length": m["body_length"] or 0,
                "patch_count": m["patch_count"],
            }
        )

    def _serialize_thread():
        return json.dumps(
            {
                "thread_id": info["thread_id"],
                "subject": info["subject"],
                "status": info["status"],
                "list_names": info["list_names"],
                "started_at": _format_date(info["started_at"]),
                "ended_at": _format_date(info["ended_at"]),
                "message_count": info["message_count"],
                "messages": formatted,
                "hint": "Use get_message with a message_id to read any message's full body.",
            },
            default=str,
        )

    output = _serialize_thread()

    if len(output) > _THREAD_BUDGET:
        # Progressively truncate older messages to fit
        for i in range(len(formatted)):
            if i >= total - recent_count:
                break
            formatted[i]["body"] = formatted[i]["body"][:100]
            formatted[i]["body_truncated"] = True
        output = _serialize_thread()

    return output


# ---------------------------------------------------------------------------
# Tool: search_patches
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_patches(
    query: str,
    list_name: str = "",
    limit: int = 10,
    offset: int = 0,
) -> str:
    """Search patches attached to PostgreSQL mailing list messages.

    Searches across patch filenames, changed file paths, and diff content.
    Useful for finding patches that modify specific PostgreSQL source files
    or contain specific code changes.

    Examples:
    - "nbtinsert.c" → patches that change nbtinsert.c
    - "vacuum" → patches with "vacuum" in filenames, file paths, or diff content
    - "src/backend/access/heap" → patches touching heap access method files

    Returns patch metadata with a diff preview. Use get_patch with a
    patch_id to retrieve the full diff.

    Args:
        query: File path, function name, or keyword to search for in patches.
        list_name: Filter by mailing list (e.g. "pgsql-hackers"). Empty = all lists.
        limit: Maximum number of results to return (1-50, default 10).
        offset: Number of results to skip for pagination (default 0).
    """
    limit, offset = _clamp_pagination(limit, offset)

    results = await search_patches_query(
        query, limit=limit, offset=offset, list_name=list_name
    )

    if not results:
        return json.dumps(
            {
                "total_results": 0,
                "patches": [],
                "hint": "No patches found. Try a broader file path or keyword.",
            }
        )

    formatted = [
        {
            "patch_id": r["patch_id"],
            "message_id": r["message_id"],
            "list_name": r["list_name"],
            "filename": r["filename"],
            "files_changed": r["files_changed"],
            "subject": r["subject"],
            "sender": r["sender"],
            "date": _format_date(r["sent_at"]),
            "diff_preview": r["diff_preview"],
        }
        for r in results
    ]

    return json.dumps(
        {
            "total_results": len(formatted),
            "patches": formatted,
            "hint": "Use get_patch with a patch_id to retrieve the full diff.",
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# Tool: get_patch
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_patch(patch_id: int) -> str:
    """Retrieve a specific patch from the PostgreSQL mailing list archive.

    Use this tool after search_patches to read the full diff of a patch.
    The patch_id comes from search_patches results.

    Returns the complete patch including: raw diff text, changed file paths,
    filename, and the associated message metadata.

    Args:
        patch_id: The numeric patch ID from search_patches results.
    """
    patch = await get_patch_by_id(patch_id)

    if patch is None:
        return json.dumps(
            {
                "error": f"Patch not found: {patch_id}",
                "hint": "Double-check the patch_id from search_patches results.",
            }
        )

    raw_diff = patch["raw_diff"] or ""
    MAX_DIFF_LENGTH = 20000
    truncated = False
    if len(raw_diff) > MAX_DIFF_LENGTH:
        raw_diff = raw_diff[:MAX_DIFF_LENGTH]
        truncated = True

    return json.dumps(
        {
            "patch_id": patch["patch_id"],
            "message_id": patch["message_id"],
            "list_name": patch["list_name"],
            "filename": patch["filename"],
            "content_type": patch["content_type"],
            "files_changed": patch["files_changed"],
            "subject": patch["subject"],
            "sender": patch["sender"],
            "date": _format_date(patch["sent_at"]),
            "raw_diff": raw_diff,
            "diff_truncated": truncated,
            "hint": "Use get_message with message_id to see the discussion context.",
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    host = os.environ.get("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_SERVER_PORT", "40000"))

    if transport == "stdio":
        logger.info("Starting MCP server with stdio transport")
        mcp.run(transport="stdio")
    else:
        logger.info("Starting MCP server on %s:%d/mcp", host, port)
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
