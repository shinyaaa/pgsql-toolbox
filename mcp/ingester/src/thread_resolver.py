"""Resolve thread structure from email References and In-Reply-To headers."""

import logging
import re

logger = logging.getLogger("ingester.thread_resolver")

_SUBJECT_PREFIX_RE = re.compile(r"^(Re|Fwd|Fw)\s*:\s*", re.IGNORECASE)


def resolve_threads(messages: list[dict]) -> None:
    """Add thread_id and thread_subject fields to each message in place."""
    by_id = {m["message_id"]: m for m in messages}

    for msg in messages:
        thread_root_id = _find_thread_root(msg, by_id)
        msg["thread_id"] = thread_root_id

        if thread_root_id in by_id:
            msg["thread_subject"] = _normalize_subject(
                by_id[thread_root_id]["subject"]
            )
        else:
            msg["thread_subject"] = _normalize_subject(msg["subject"])


def _find_thread_root(msg: dict, by_id: dict[str, dict]) -> str:
    # References[0] is the thread root per RFC 2822
    refs = msg.get("references", [])
    if refs:
        return refs[0]

    # Fallback: walk In-Reply-To chain
    parent = msg.get("parent_id")
    if parent:
        visited: set[str] = set()
        current = parent
        while current in by_id and current not in visited:
            visited.add(current)
            grandparent = by_id[current].get("parent_id")
            if grandparent:
                current = grandparent
            else:
                break
        return current

    return msg["message_id"]


def _normalize_subject(subject: str) -> str:
    while _SUBJECT_PREFIX_RE.match(subject):
        subject = _SUBJECT_PREFIX_RE.sub("", subject, count=1).strip()
    return subject
