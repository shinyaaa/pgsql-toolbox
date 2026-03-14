"""Parse mbox files into structured message dicts with patch extraction."""

import email
import email.header
import email.utils
import logging
import mailbox
import re
import warnings
from datetime import datetime, timedelta, timezone

from dateutil import parser as dateutil_parser
from dateutil.parser import UnknownTimezoneWarning

warnings.filterwarnings("ignore", category=UnknownTimezoneWarning)

logger = logging.getLogger("ingester.mbox_parser")

DIFF_HEADER_RE = re.compile(
    r"^diff --git a/.+ b/.+$|"
    r"^--- a/.+$|"
    r"^\+\+\+ b/.+$|"
    r"^@@ .+ @@",
    re.MULTILINE,
)

DIFF_FILES_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)

PATCH_CONTENT_TYPES = {
    "text/x-patch",
    "text/x-diff",
    "application/x-patch",
    "application/x-diff",
}

PATCH_EXTENSIONS = {".patch", ".diff"}

_QUOTE_LINE_RE = re.compile(r"^\s*>")


def strip_email_quotes(body: str) -> str:
    """Remove quoted lines and their attribution headers from email body.

    Strips lines starting with '>' (email quotes) and single-line attribution
    headers ending with 'wrote:' that immediately precede a quoted block.
    Collapses excessive blank lines left by removal.
    """
    if not body:
        return body

    lines = body.splitlines()
    is_quoted = [bool(_QUOTE_LINE_RE.match(line)) for line in lines]

    result: list[str] = []
    for i, line in enumerate(lines):
        if is_quoted[i]:
            continue
        # Remove attribution line ("... wrote:") right before a quoted block
        stripped = line.rstrip()
        if (
            stripped.endswith(":")
            and "wrote" in stripped.lower()
            and i + 1 < len(lines)
            and is_quoted[i + 1]
        ):
            continue
        result.append(line)

    text = "\n".join(result)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_decode(data: bytes, charset: str | None) -> str:
    """Decode bytes with fallback for unknown/broken charsets.

    Strips NUL bytes which PostgreSQL TEXT columns cannot store.
    """
    for enc in (charset, "utf-8", "latin-1"):
        if not enc:
            continue
        try:
            return data.decode(enc, errors="replace").replace("\x00", "")
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("latin-1", errors="replace").replace("\x00", "")


def decode_header(raw: str | None) -> str:
    if not raw:
        return ""
    parts = email.header.decode_header(raw)
    decoded = []
    for content, charset in parts:
        if isinstance(content, bytes):
            decoded.append(_safe_decode(content, charset))
        else:
            decoded.append(content)
    return " ".join(decoded)


def clean_message_id(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = str(raw).strip()
    if raw.startswith("<") and raw.endswith(">"):
        return raw[1:-1]
    return raw


def parse_references(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [mid[1:-1] for mid in re.findall(r"<[^>]+>", str(raw))]


def _sanitize_datetime(dt: datetime) -> datetime:
    """Ensure timezone offset is within ±24h (required by psycopg/PostgreSQL)."""
    if dt.tzinfo is not None:
        offset = dt.utcoffset()
        if offset is not None and abs(offset) >= timedelta(hours=24):
            return dt.replace(tzinfo=timezone.utc)
    return dt


def _ensure_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware; assume UTC if naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = str(raw)
    try:
        return _ensure_aware(_sanitize_datetime(dateutil_parser.parse(raw)))
    except (ValueError, OverflowError, TypeError):
        try:
            return _ensure_aware(_sanitize_datetime(email.utils.parsedate_to_datetime(raw)))
        except Exception:
            logger.debug("Could not parse date: %s", raw)
            return None


def extract_body(msg: email.message.Message) -> str:
    if not msg.is_multipart():
        if msg.get_content_type() == "text/plain":
            payload = msg.get_payload(decode=True)
            if payload:
                return _safe_decode(payload, msg.get_content_charset("utf-8"))
        return ""

    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            if part.get_content_disposition() == "attachment":
                continue
            payload = part.get_payload(decode=True)
            if payload:
                return _safe_decode(payload, part.get_content_charset("utf-8"))
    return ""


def extract_patches(msg: email.message.Message, body: str) -> list[dict]:
    patches = []

    # 1. Check MIME attachments
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = part.get_content_disposition()
            filename = part.get_filename() or ""

            is_patch_type = content_type in PATCH_CONTENT_TYPES
            is_patch_ext = any(
                filename.lower().endswith(ext) for ext in PATCH_EXTENSIONS
            )

            if is_patch_type or (disposition == "attachment" and is_patch_ext):
                payload = part.get_payload(decode=True)
                if payload:
                    diff_text = _safe_decode(payload, part.get_content_charset("utf-8"))
                    files = DIFF_FILES_RE.findall(diff_text)
                    files_changed = list(set(f for pair in files for f in pair))
                    patches.append(
                        {
                            "filename": filename or "attachment",
                            "content_type": content_type,
                            "files_changed": files_changed,
                            "raw_diff": diff_text,
                        }
                    )

    # 2. Check for inline diffs in body (only if no attachment patches found)
    if not patches and body and DIFF_HEADER_RE.search(body):
        files = DIFF_FILES_RE.findall(body)
        files_changed = list(set(f for pair in files for f in pair))
        if files_changed:
            patches.append(
                {
                    "filename": "inline",
                    "content_type": "text/plain",
                    "files_changed": files_changed,
                    "raw_diff": body,
                }
            )

    return patches


def parse_mbox(filepath: str) -> list[dict]:
    mbox = mailbox.mbox(filepath)
    messages = []
    skipped = 0
    errors = 0

    keys = list(mbox.keys())
    for key in keys:
        try:
            msg = mbox[key]
        except Exception:
            errors += 1
            continue
        msg_id = clean_message_id(msg.get("Message-ID"))
        if not msg_id:
            skipped += 1
            continue

        raw_body = extract_body(msg)
        patches = extract_patches(msg, raw_body)
        body = strip_email_quotes(raw_body)

        messages.append(
            {
                "message_id": msg_id,
                "parent_id": clean_message_id(msg.get("In-Reply-To")),
                "references": parse_references(msg.get("References")),
                "sender": decode_header(msg.get("From", "")),
                "sent_at": parse_date(msg.get("Date")),
                "subject": decode_header(msg.get("Subject", "")),
                "body": body,
                "body_raw": raw_body,
                "patches": patches,
            }
        )

    if skipped:
        logger.warning(
            "Skipped %d messages without Message-ID in %s", skipped, filepath
        )
    if errors:
        logger.warning(
            "Failed to read %d messages in %s", errors, filepath
        )

    mbox.close()
    return messages
