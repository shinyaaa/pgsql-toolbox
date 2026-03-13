"""pg_init logic: create PostgreSQL development worktrees.

Ported from the original bash script bin/pg_init.
"""

import fcntl
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from lib.config import (
    CLAUDE_STARTUP_BUFFER,
    CLAUDE_STARTUP_POLL_INTERVAL,
    CLAUDE_STARTUP_TIMEOUT,
    GH_REPO,
    LOGS_DIR,
    MAIN_REPO,
    MCP_ENDPOINT,
    PGSQL_DIR,
    PORT_LOCK,
    PRIMARY_PORT_MIN,
    PRIMARY_PORT_MAX,
    REPO_ROOT,
    SYNC_BRANCHES,
    standby_port,
)
from lib.operations import atomic_write, make_run_wrapper

_default_logger = logging.getLogger("pg_init")
_default_run = make_run_wrapper(_default_logger)
_local = threading.local()


class _LoggerProxy:
    """Thread-aware proxy: uses per-invocation logger if set, else the default."""

    def __getattr__(self, name):
        real = getattr(_local, 'logger', _default_logger)
        return getattr(real, name)


class _RunProxy:
    """Thread-aware proxy: uses per-invocation _run if set, else the default."""

    def __call__(self, *args, **kwargs):
        real = getattr(_local, 'run', _default_run)
        return real(*args, **kwargs)


logger = _LoggerProxy()  # type: ignore[assignment]
_run = _RunProxy()


def _make_logger(log_file: Path) -> logging.Logger:
    """Create a per-invocation logger that writes to both file and stdout.

    Uses a unique logger name per log file to avoid thread-safety issues
    when multiple init_branch() calls run concurrently.
    """
    inv_logger = logging.getLogger(f"pg_init.{log_file.stem}")
    inv_logger.setLevel(logging.INFO)
    inv_logger.propagate = False

    # Clear any stale handlers (e.g. from a previous run with the same name)
    for h in inv_logger.handlers[:]:
        inv_logger.removeHandler(h)
        h.close()

    fmt = logging.Formatter("%(message)s")

    fh = logging.FileHandler(str(log_file))
    fh.setFormatter(fmt)
    inv_logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    inv_logger.addHandler(sh)

    return inv_logger


def setup_logging(log_file: Optional[Path] = None) -> Path:
    """Determine the log file path, creating the log directory if needed.

    Returns the log file path.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if log_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = LOGS_DIR / f"pg_init_{timestamp}.log"
    return log_file


def sync_upstream():
    """Sync fork with upstream for all tracked branches."""
    logger.info("Syncing upstream branches...")
    for branch in SYNC_BRANCHES:
        try:
            _run(["gh", "repo", "sync", GH_REPO, "-b", branch], check=False)
        except Exception as e:
            logger.info(f"Warning: failed to sync {branch}: {e}")


def allocate_port(project: str, branch: str) -> int:
    """Allocate a port for the project using flock-based locking.

    Returns the allocated port number.
    """
    PORT_LOCK.touch(exist_ok=True)

    fd = os.open(str(PORT_LOCK), os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)

        # Read and prune stale entries
        content = PORT_LOCK.read_text()
        latest: Dict[str, str] = {}
        for line in content.splitlines():
            parts = line.strip().split()
            if not parts or parts[0].startswith("#"):
                continue
            if len(parts) < 3:
                continue
            lp, lproj, lbranch = parts[0], parts[1], parts[2]
            # Enforce master-only for the master port
            if lp == str(PRIMARY_PORT_MIN) and lbranch != "master":
                continue
            # Keep only if project directory exists
            if (PGSQL_DIR / lproj).is_dir():
                latest[lproj] = f"{lp} {lproj} {lbranch}"

        # Rewrite pruned, deduplicated entries
        atomic_write(
            PORT_LOCK,
            "\n".join(latest.values()) + "\n" if latest else "",
        )

        # Check if project already exists on disk
        if (PGSQL_DIR / project).is_dir():
            raise RuntimeError(f"Already exists {PGSQL_DIR / project}")

        # Reuse existing allocation if registered
        for line_val in latest.values():
            parts = line_val.split()
            if parts[1] == project:
                return int(parts[0])

        # Allocate new port
        if branch == "master":
            port = PRIMARY_PORT_MIN
            # Check if master port is already taken by another project
            for line_val in latest.values():
                parts = line_val.split()
                if parts[0] == str(PRIMARY_PORT_MIN) and parts[1] != project:
                    raise RuntimeError(
                        f"Port {PRIMARY_PORT_MIN} is already allocated to "
                        f"project: {parts[1]}"
                    )
        else:
            used_ports = set()
            for line_val in latest.values():
                parts = line_val.split()
                used_ports.add(int(parts[0]))

            port = None
            for p in range(PRIMARY_PORT_MIN + 1, PRIMARY_PORT_MAX + 1):
                if p not in used_ports:
                    port = p
                    break
            if port is None:
                raise RuntimeError(
                    f"No free port available in range "
                    f"{PRIMARY_PORT_MIN + 1}-{PRIMARY_PORT_MAX}"
                )

        # Register allocation
        with open(str(PORT_LOCK), "a") as f:
            f.write(f"{port} {project} {branch}\n")

        logger.info(f"Assigned port: {port} (branch: {branch})")
        return port

    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def update_base_repo():
    """Fetch and update the base repository's master branch."""
    if not (MAIN_REPO / ".git").exists():
        raise RuntimeError(
            f"Base repository not found at {MAIN_REPO}\n"
            "Please clone your postgres repo there (master branch)."
        )

    logger.info("Updating base repository...")
    _run(["git", "fetch", "--all", "--tags"], cwd=str(MAIN_REPO), check=False)

    # Checkout master
    result = _run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/master"],
        cwd=str(MAIN_REPO), check=False, capture=True,
    )
    if result.returncode == 0:
        _run(["git", "checkout", "master"], cwd=str(MAIN_REPO), check=False)
    else:
        _run(
            ["git", "checkout", "-B", "master", "origin/master"],
            cwd=str(MAIN_REPO), check=False,
        )

    _run(["git", "pull", "--ff-only", "origin", "master"],
         cwd=str(MAIN_REPO), check=False)


def cleanup_branches():
    """Prune worktrees and delete unnecessary local branches."""
    logger.info("Cleaning up branches...")
    _run(["git", "worktree", "prune"], cwd=str(MAIN_REPO), check=False)

    # Get branches checked out by worktrees
    result = _run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(MAIN_REPO), capture=True, check=False,
    )
    wt_branches = set()
    if result.stdout:
        for line in result.stdout.splitlines():
            if line.startswith("branch "):
                ref = line.split(" ", 1)[1]
                wt_branches.add(ref.replace("refs/heads/", ""))

    # Get all local branches
    result = _run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
        cwd=str(MAIN_REPO), capture=True, check=False,
    )
    local_branches = result.stdout.strip().splitlines() if result.stdout else []

    # Read port_lock projects
    port_lock_projects = set()
    if PORT_LOCK.exists():
        for line in PORT_LOCK.read_text().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                port_lock_projects.add(parts[1])

    for b in local_branches:
        if b == "master":
            continue
        if b in wt_branches:
            continue
        if (PGSQL_DIR / b).is_dir():
            continue
        if b in port_lock_projects:
            continue
        _run(["git", "branch", "-D", b], cwd=str(MAIN_REPO), check=False)


def setup_worktree(branch: str, base_branch: str) -> Path:
    """Create or reuse a git worktree for the selected ref.

    Returns the source directory path.
    """
    if branch == "master":
        logger.info(f"Using master repository: {MAIN_REPO}")
        return MAIN_REPO

    src_dir = PGSQL_DIR / branch / "postgres"
    if (src_dir / ".git").exists():
        logger.info(f"Using existing worktree: {src_dir}")
        return src_dir

    logger.info(f"Creating worktree for {branch} at {src_dir}")
    _run(["git", "fetch", "--all", "--tags"], cwd=str(MAIN_REPO))

    # Try in order: remote branch, local branch, tag, new branch from base
    def ref_exists(ref):
        r = _run(
            ["git", "rev-parse", "-q", "--verify", ref],
            cwd=str(MAIN_REPO), check=False, capture=True,
        )
        return r.returncode == 0

    if ref_exists(f"refs/remotes/origin/{branch}"):
        _run(["git", "worktree", "add", "-B", branch, str(src_dir),
              f"origin/{branch}"], cwd=str(MAIN_REPO))
    elif ref_exists(f"refs/heads/{branch}"):
        _run(["git", "worktree", "add", "-B", branch, str(src_dir),
              branch], cwd=str(MAIN_REPO))
    elif ref_exists(f"refs/tags/{branch}"):
        _run(["git", "worktree", "add", "--detach", str(src_dir),
              f"refs/tags/{branch}"], cwd=str(MAIN_REPO))
    else:
        # Create new branch from base
        if ref_exists(f"refs/remotes/origin/{base_branch}"):
            base_ref = f"origin/{base_branch}"
        elif ref_exists(f"refs/heads/{base_branch}"):
            base_ref = base_branch
        elif ref_exists(f"refs/tags/{base_branch}"):
            base_ref = f"refs/tags/{base_branch}"
        else:
            base_ref = "origin/master"
        _run(["git", "worktree", "add", "-B", branch, str(src_dir),
              base_ref], cwd=str(MAIN_REPO))

    return src_dir


def copy_settings(src_dir: Path):
    """Copy agent settings from skel/ to the worktree."""
    skel_dir = REPO_ROOT / "skel"
    if not skel_dir.is_dir():
        logger.warning(f"skel directory not found: {skel_dir}")
        return

    for item in skel_dir.iterdir():
        dest = src_dir / item.name
        if item.is_dir():
            logger.info(f"Copying {item.name}/")
            if dest.exists():
                shutil.rmtree(str(dest))
            shutil.copytree(str(item), str(dest))
        else:
            logger.info(f"Copying {item.name}")
            shutil.copy2(str(item), str(dest))

    # Install MCP server
    _run(["claude", "mcp", "add", "--transport", "http",
          "pgsql-ml-mcp", MCP_ENDPOINT],
         cwd=str(src_dir), check=False)


def build_postgres(src_dir: Path, project_dir: Path, port: int):
    """Configure and build PostgreSQL."""
    logger.info("Configuring PostgreSQL...")
    _run([
        "./configure",
        "--enable-debug", "--enable-cassert", "--enable-tap-tests",
        "--without-icu",
        f"--with-pgport={port}",
        f"--prefix={project_dir}",
        "CFLAGS=-O0",
    ], cwd=str(src_dir))

    nproc = os.cpu_count() or 1
    logger.info(f"Building PostgreSQL (make -j{nproc})...")
    _run(["make", "-s", "world", f"-j{nproc}"], cwd=str(src_dir))

    logger.info("Installing PostgreSQL...")
    _run(["make", "-s", "install-world"], cwd=str(src_dir))

    logger.info("Building pg_bsd_indent...")
    _run(["make", "-s"], cwd=str(src_dir / "src" / "tools" / "pg_bsd_indent"))
    _run(["make", "-s", "install"],
         cwd=str(src_dir / "src" / "tools" / "pg_bsd_indent"))


def _setup_envrc(src_dir: Path, project_dir: Path, port: int):
    """Create .envrc for direnv."""
    envrc = src_dir / ".envrc"
    envrc_lines = [
        f"export PGPORT={port}",
        f"export PGDATA={project_dir}/data",
        f"export PGDATABASE=postgres",
        f"export PGPATH={project_dir}",
        f"PATH_add {project_dir}/bin",
        f"PATH_add {src_dir}/src/tools/pgindent",
    ]
    envrc.write_text("\n".join(envrc_lines) + "\n")
    _run(["direnv", "allow"], cwd=str(src_dir), check=False)


def _setup_standby_wrappers(project_dir: Path, port: int, standbys: list):
    """Create convenience wrapper scripts for standbys in project bin/."""
    bin_dir = project_dir / "bin"
    for i, sb in enumerate(standbys, 1):
        sb_port = standby_port(port, i)
        sb_data = project_dir / f"data-s{i}"

        # psql-s{i}: shortcut for psql to standby
        psql_wrapper = bin_dir / f"psql-s{i}"
        psql_wrapper.write_text(
            f"#!/bin/sh\nexec psql -p {sb_port} \"$@\"\n"
        )
        psql_wrapper.chmod(0o755)

        # pg-s{i}: run any command with PGPORT/PGDATA set to standby
        pg_wrapper = bin_dir / f"pg-s{i}"
        pg_wrapper.write_text(
            f"#!/bin/sh\nexport PGPORT={sb_port}\n"
            f"export PGDATA={sb_data}\nexec \"$@\"\n"
        )
        pg_wrapper.chmod(0o755)


def _setup_git_excludes(src_dir: Path):
    """Add generated paths to the worktree's git exclude file."""
    result = _run(
        ["git", "rev-parse", "--git-path", "info/exclude"],
        cwd=str(src_dir), capture=True,
    )
    exclude_file = Path(result.stdout.strip())
    if not exclude_file.is_absolute():
        exclude_file = src_dir / exclude_file
    exclude_file.parent.mkdir(parents=True, exist_ok=True)

    existing = exclude_file.read_text() if exclude_file.exists() else ""
    patterns = ["work/", ".vscode/", ".envrc", "AGENTS.md", ".claude/"]
    with open(str(exclude_file), "a") as f:
        for pat in patterns:
            if pat not in existing.splitlines():
                f.write(f"{pat}\n")


def _setup_memo(project_dir: Path, branch: str):
    """Create a memo file for the branch."""
    memo_dir = project_dir / "postgres" / "work" / branch
    memo_dir.mkdir(parents=True, exist_ok=True)
    memo_file = memo_dir / f"{branch}.md"
    memo_file.touch(exist_ok=True)


def setup_environment(src_dir: Path, project_dir: Path, port: int, branch: str,
                      standbys: Optional[list] = None):
    """Create .envrc, work/ directory, git excludes, and memo file."""
    logger.info("Setting up environment...")

    # Create work/ and .vscode/
    (src_dir / "work").mkdir(exist_ok=True)
    (src_dir / ".vscode").mkdir(exist_ok=True)

    _setup_envrc(src_dir, project_dir, port)
    if standbys:
        _setup_standby_wrappers(project_dir, port, standbys)
    _setup_git_excludes(src_dir)
    _setup_memo(project_dir, branch)


def init_database(project_dir: Path, port: int):
    """Run initdb, configure postgresql.conf, and start PostgreSQL."""
    initdb = project_dir / "bin" / "initdb"
    data_dir = project_dir / "data"

    logger.info("Running initdb...")
    _run([str(initdb), "--encoding=utf8", "--no-locale", "-D", str(data_dir)])

    # Enable logging_collector
    conf = data_dir / "postgresql.conf"
    with open(str(conf), "a") as f:
        f.write("logging_collector = on\n")

    # Start PostgreSQL
    # pg_ctl start forks a background process; using PIPE would block
    # because the child inherits the pipe fd. Use DEVNULL instead.
    pg_ctl = project_dir / "bin" / "pg_ctl"
    logger.info(f"Starting PostgreSQL on port {port}...")
    result = subprocess.run(
        [str(pg_ctl), "-D", str(data_dir), "-o", f"-p {port}", "start"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_ctl start failed (exit {result.returncode})")
    logger.info("PostgreSQL started.")


def setup_tmux_claude(branch: str, src_dir: Path):
    """Create a tmux session and start Claude Code."""
    session = branch

    # Check if session already exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        logger.info(f"tmux session '{session}' already exists, skipping creation.")
        return

    logger.info(f"Creating tmux session '{session}'...")
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, "-c", str(src_dir)],
        capture_output=True, text=True,
    )

    # Start Claude Code
    subprocess.run(
        ["tmux", "send-keys", "-t", session, "claude", "Enter"],
        capture_output=True, text=True,
    )

    # Wait for Claude Code prompt (poll quietly, no logging)
    logger.info("Waiting for Claude Code to start...")
    for i in range(CLAUDE_STARTUP_TIMEOUT):
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session, "-p"],
            capture_output=True, text=True,
        )
        if result.stdout:
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            # Claude Code prompt: ">" or "❯" or contains input marker
            if lines and (lines[-1].startswith(">") or "❯" in lines[-1]):
                break
        time.sleep(CLAUDE_STARTUP_POLL_INTERVAL)

    time.sleep(CLAUDE_STARTUP_BUFFER)
    subprocess.run(
        ["tmux", "send-keys", "-t", session, f"/rename {branch}", "Enter"],
        capture_output=True, text=True,
    )

    logger.info(f"tmux session '{session}' created with Claude Code running.")
    logger.info(f"  Attach: tmux attach -t {session}")


def init_branch(branch: str, base_branch: str = "master",
                standbys: Optional[list] = None,
                log_file: Optional[Path] = None) -> Path:
    """Initialize a complete PostgreSQL development environment.

    This is the main entry point that orchestrates the full setup:
    1. Sync upstream branches
    2. Allocate port
    3. Update base repo
    4. Clean up stale branches
    5. Create/reuse git worktree
    6. Copy settings
    7. Build PostgreSQL
    8. Set up environment
    9. Initialize database
    10. Setup replication (if standbys specified)
    11. Start tmux + Claude Code

    Args:
        standbys: Optional list of dicts, e.g. [{"type": "streaming_sync"}, {"type": "streaming_async"}]

    Returns the log file path.
    """
    log_path = setup_logging(log_file)

    # Set up per-invocation logger and run wrapper (thread-safe via threading.local)
    inv_logger = _make_logger(log_path)
    _local.logger = inv_logger
    _local.run = make_run_wrapper(inv_logger)

    project = branch
    project_dir = PGSQL_DIR / project

    try:
        logger.info(f"Initializing PostgreSQL environment for branch: {branch}")
        logger.info(f"Base branch: {base_branch}")
        if standbys:
            logger.info(f"Standbys: {', '.join(s['type'] for s in standbys)}")

        # 1. Sync upstream
        sync_upstream()

        # 2. Allocate port
        port = allocate_port(project, branch)

        # 3. Create project directory
        project_dir.mkdir(parents=True, exist_ok=True)

        # 4. Update base repo
        update_base_repo()

        # 5. Clean up branches
        cleanup_branches()

        # 6. Create worktree
        src_dir = setup_worktree(branch, base_branch)

        # 7. Copy settings
        copy_settings(src_dir)

        # 8. Build PostgreSQL
        build_postgres(src_dir, project_dir, port)

        # 9. Setup environment
        setup_environment(src_dir, project_dir, port, branch, standbys)

        # 10. Initialize database
        init_database(project_dir, port)

        # 11. Setup replication
        if standbys:
            from lib.db import add_standby
            from lib.replication import configure_primary, create_standby

            logger.info("")
            logger.info("Setting up replication cluster...")
            configure_primary(project_dir, port, standbys)

            for i, sb in enumerate(standbys, 1):
                create_standby(project_dir, port, i, sb["type"])
                add_standby(branch, i, sb["type"])

            logger.info("Replication cluster setup complete!")

        # 12. Setup tmux + Claude Code
        setup_tmux_claude(branch, src_dir)

        logger.info("")
        logger.info("PostgreSQL development environment setup complete!")
        logger.info(f"You can access the database with the following command:")
        logger.info(f"  {project_dir}/bin/psql -p {port} postgres")
        if standbys:
            for i in range(1, len(standbys) + 1):
                sb_port = standby_port(port, i)
                logger.info(f"  {project_dir}/bin/psql -p {sb_port} postgres  (standby S{i})")
        logger.info(f"Log file: {log_path}")

    except Exception:
        logger.exception("pg_init failed")
        raise
    finally:
        # Clean up per-invocation logger handlers and thread-local state
        for h in inv_logger.handlers[:]:
            inv_logger.removeHandler(h)
            h.close()
        _local.logger = None
        _local.run = None

    return log_path
