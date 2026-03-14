"""Heuristic thread status classifier for PostgreSQL mailing list threads.

Scans message bodies within a thread to determine the thread's status:
- committed: patch was committed/pushed
- withdrawn: author withdrew the patch
- returned: patch returned with feedback
- patch_proposed: has patches but no resolution signal
- discussion: general discussion (default)
"""

import re

# ---------------------------------------------------------------------------
# Keyword patterns (compiled, case-insensitive)
# ---------------------------------------------------------------------------

# Patterns that signal a patch was committed.
# Focus on phrases committers typically use when confirming a push.
_COMMITTED_PATTERNS = [
    re.compile(r"\bpushed\b", re.IGNORECASE),
    re.compile(r"\bcommitted\b", re.IGNORECASE),
    re.compile(r"\bapplied to\b", re.IGNORECASE),
    re.compile(r"\bI[''']ve pushed\b", re.IGNORECASE),
    re.compile(r"\bI pushed\b", re.IGNORECASE),
    re.compile(r"\bI[''']ve committed\b", re.IGNORECASE),
    re.compile(r"\bI committed\b", re.IGNORECASE),
    re.compile(r"\bI[''']ve applied\b", re.IGNORECASE),
    re.compile(r"\bmerged\b", re.IGNORECASE),
]

# Patterns that signal the author withdrew the patch.
_WITHDRAWN_PATTERNS = [
    re.compile(r"\bwithdraw(?:ing|n)?\b", re.IGNORECASE),
    re.compile(r"\bI[''']m dropping this\b", re.IGNORECASE),
    re.compile(r"\bdropping this patch\b", re.IGNORECASE),
    re.compile(r"\babandoning this\b", re.IGNORECASE),
]

# Patterns that signal the patch was returned for more work.
_RETURNED_PATTERNS = [
    re.compile(r"\breturned with feedback\b", re.IGNORECASE),
    re.compile(r"\bsending back\b", re.IGNORECASE),
    re.compile(r"\bmarked as returned\b", re.IGNORECASE),
    re.compile(r"\bneeds? (?:more )?(?:work|revision)\b", re.IGNORECASE),
]

# Lines starting with ">" are quoted text — we want to skip them
# to avoid false positives from quoted content.
_QUOTE_LINE_RE = re.compile(r"^\s*>", re.MULTILINE)


def _strip_quoted_lines(body: str) -> str:
    """Remove lines that are email quotes (start with '>') to reduce false positives."""
    lines = body.splitlines()
    return "\n".join(line for line in lines if not _QUOTE_LINE_RE.match(line))


def _match_any(text: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in patterns)


def classify_thread(
    messages: list[str],
    has_patches: bool,
) -> str:
    """Classify a thread's status based on message bodies.

    Args:
        messages: Message bodies ordered chronologically (oldest first).
        has_patches: Whether the thread has any associated patches.

    Returns:
        One of: 'committed', 'withdrawn', 'returned', 'patch_proposed', 'discussion'.
    """
    if not messages:
        return "discussion"

    total = len(messages)
    # Focus on the latter half of the thread where conclusions appear.
    # For short threads (<=4 messages), check all messages.
    latter_start = max(0, total - max(total // 2, 2))

    # Check latter messages first (higher priority)
    for body in reversed(messages[latter_start:]):
        clean = _strip_quoted_lines(body) if body else ""
        if not clean:
            continue

        if _match_any(clean, _COMMITTED_PATTERNS):
            return "committed"
        if _match_any(clean, _WITHDRAWN_PATTERNS):
            return "withdrawn"
        if _match_any(clean, _RETURNED_PATTERNS):
            return "returned"

    # If no resolution signal found, check if it's a patch thread
    if has_patches:
        return "patch_proposed"

    return "discussion"
