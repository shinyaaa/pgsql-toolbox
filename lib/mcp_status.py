"""MCP server status, mbox inventory, and daily ingestion batch."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path

from lib.config import (
    MCP_BATCH_HOUR,
    MCP_BATCH_MINUTE,
    MCP_COMPOSE_FILE,
    MCP_DIR,
    MCP_DOWNLOAD_SCRIPT,
    MCP_LISTS,
    MCP_MBOX_DIR,
)

log = logging.getLogger(__name__)

_batch_lock = threading.Lock()
_batch_state = {"status": "idle", "started_at": None, "finished_at": None,
                "last_result": None, "error": None}


def _compose_cmd(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(MCP_COMPOSE_FILE), *args]


def get_service_status() -> list[dict]:
    """Return docker compose service states (db, mcp-server)."""
    try:
        result = subprocess.run(
            _compose_cmd("ps", "--format", "json"),
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return [{"error": str(e)}]

    if result.returncode != 0:
        return [{"error": result.stderr.strip() or "docker compose ps failed"}]

    services = []
    raw = result.stdout.strip()
    if not raw:
        return services
    # Newer compose emits one JSON object per line; older emits a JSON array
    if raw.startswith("["):
        try:
            services = json.loads(raw)
        except json.JSONDecodeError:
            return [{"error": "failed to parse compose ps output"}]
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                services.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return [
        {
            "name": s.get("Service") or s.get("Name"),
            "state": s.get("State"),
            "status": s.get("Status"),
            "health": s.get("Health"),
        }
        for s in services
    ]


def get_mbox_inventory() -> dict:
    """Per-list mbox file inventory and overall last-updated timestamp."""
    lists = []
    overall_mtime: float | None = None
    if MCP_MBOX_DIR.exists():
        for list_dir in sorted(p for p in MCP_MBOX_DIR.iterdir() if p.is_dir()):
            files = [f for f in list_dir.iterdir()
                     if f.is_file() and f.name != ".gitkeep"]
            if not files:
                continue
            latest = max(f.stat().st_mtime for f in files)
            total = sum(f.stat().st_size for f in files)
            if overall_mtime is None or latest > overall_mtime:
                overall_mtime = latest
            lists.append({
                "name": list_dir.name,
                "file_count": len(files),
                "total_size": total,
                "last_updated": datetime.fromtimestamp(latest).isoformat(),
                "latest_file": max(files, key=lambda f: f.stat().st_mtime).name,
            })
    return {
        "lists": lists,
        "last_updated": datetime.fromtimestamp(overall_mtime).isoformat()
        if overall_mtime else None,
    }


def get_status() -> dict:
    return {
        "services": get_service_status(),
        "mbox": get_mbox_inventory(),
        "batch": batch_state(),
    }


def batch_state() -> dict:
    with _batch_lock:
        return dict(_batch_state)


def _set_batch(**kw) -> None:
    with _batch_lock:
        _batch_state.update(kw)


def _yyyymm(d: datetime) -> str:
    return d.strftime("%Y%m")


def _previous_month(d: datetime) -> datetime:
    first = d.replace(day=1)
    return first - timedelta(days=1)


def _run_download(list_name: str, start_yyyymm: str, end_yyyymm: str) -> str:
    out_dir = MCP_MBOX_DIR / list_name
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["bash", str(MCP_DOWNLOAD_SCRIPT),
           list_name, start_yyyymm, end_yyyymm, str(MCP_MBOX_DIR)]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=str(MCP_DIR), timeout=600)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise RuntimeError(f"download_mbox.sh failed for {list_name}: {output}")
    return output


def _run_ingest() -> str:
    cmd = _compose_cmd("run", "--rm", "ingester")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise RuntimeError(f"ingester failed: {output}")
    return output


def run_batch(lists: list[str] | None = None) -> dict:
    """Download previous+current month for each list and run the ingester."""
    lists = lists or MCP_LISTS
    now = datetime.now()
    end = _yyyymm(now)
    start = _yyyymm(_previous_month(now))

    _set_batch(status="running", started_at=now.isoformat(),
               finished_at=None, error=None,
               last_result={"lists": lists, "range": f"{start}-{end}"})
    log.info("MCP batch start: lists=%s range=%s..%s", lists, start, end)
    try:
        download_log = []
        for name in lists:
            download_log.append(_run_download(name, start, end))
        ingest_log = _run_ingest()
        finished = datetime.now().isoformat()
        result = {
            "lists": lists,
            "range": f"{start}-{end}",
            "download_log": "\n".join(download_log)[-4000:],
            "ingest_log": ingest_log[-4000:],
        }
        _set_batch(status="idle", finished_at=finished, last_result=result)
        log.info("MCP batch done")
        return result
    except Exception as e:
        finished = datetime.now().isoformat()
        _set_batch(status="idle", finished_at=finished, error=str(e))
        log.exception("MCP batch failed")
        raise


def trigger_batch_async() -> bool:
    """Start a batch in a background thread. Returns False if already running."""
    with _batch_lock:
        if _batch_state["status"] == "running":
            return False
        _batch_state["status"] = "running"
    threading.Thread(target=_batch_thread, daemon=True).start()
    return True


def _batch_thread() -> None:
    try:
        run_batch()
    except Exception:
        pass


def _seconds_until_next_run() -> float:
    now = datetime.now()
    target = now.replace(hour=MCP_BATCH_HOUR, minute=MCP_BATCH_MINUTE,
                         second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _scheduler_loop() -> None:
    while True:
        delay = _seconds_until_next_run()
        log.info("Next MCP batch in %.0f seconds", delay)
        threading.Event().wait(delay)
        try:
            run_batch()
        except Exception:
            pass


_scheduler_started = False


def start_scheduler() -> None:
    """Start daily batch scheduler thread (idempotent)."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    threading.Thread(target=_scheduler_loop, daemon=True,
                     name="mcp-batch-scheduler").start()
    log.info("MCP batch scheduler started (%02d:%02d daily)",
             MCP_BATCH_HOUR, MCP_BATCH_MINUTE)
