"""pg_init logic: create PostgreSQL development worktrees.

Ported from the original bash script bin/pg_init.
"""

import fcntl
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from lib.config import (
    GH_REPO,
    LOGS_DIR,
    MAIN_REPO,
    PGSQL_DIR,
    PORT_LOCK,
    REPO_ROOT,
    SYNC_BRANCHES,
)

logger = logging.getLogger("pg_init")


def setup_logging(log_file: Optional[Path] = None) -> Path:
    """Configure logging to both file and stdout (replaces bash tee).

    Returns the log file path.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if log_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = LOGS_DIR / f"pg_init_{timestamp}.log"

    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(message)s")

    fh = logging.FileHandler(str(log_file))
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return log_file


def _run(cmd, check=True, capture=False, cwd=None, timeout=None):
    """Run a subprocess command, logging the command and any errors."""
    cmd_str = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    logger.info(f"+ {cmd_str}")
    kwargs = {
        "cwd": cwd,
        "timeout": timeout,
        "text": True,
    }
    if capture:
        kwargs["capture_output"] = True
    else:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT
    result = subprocess.run(cmd, **kwargs)
    if not capture and result.stdout:
        for line in result.stdout.splitlines():
            logger.info(line)
    if check and result.returncode != 0:
        error = result.stderr if capture else (result.stdout or "")
        raise RuntimeError(f"Command failed (exit {result.returncode}): {cmd_str}\n{error}")
    return result


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
        latest: dict[str, str] = {}
        for line in content.splitlines():
            parts = line.strip().split()
            if not parts or parts[0].startswith("#"):
                continue
            if len(parts) < 3:
                continue
            lp, lproj, lbranch = parts[0], parts[1], parts[2]
            # Enforce master-only for port 50000
            if lp == "50000" and lbranch != "master":
                continue
            # Keep only if project directory exists
            if (PGSQL_DIR / lproj).is_dir():
                latest[lproj] = f"{lp} {lproj} {lbranch}"

        # Rewrite pruned, deduplicated entries
        PORT_LOCK.write_text(
            "\n".join(latest.values()) + "\n" if latest else ""
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
            port = 50000
            # Check if 50000 is already taken by another project
            for line_val in latest.values():
                parts = line_val.split()
                if parts[0] == "50000" and parts[1] != project:
                    raise RuntimeError(
                        f"Port 50000 is already allocated to project: {parts[1]}"
                    )
        else:
            used_ports = set()
            for line_val in latest.values():
                parts = line_val.split()
                used_ports.add(int(parts[0]))

            port = None
            for p in range(50001, 60000):
                if p not in used_ports:
                    port = p
                    break
            if port is None:
                raise RuntimeError("No free port available in range 50001-59999")

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
    import shutil

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
          "pgsql-ml-mcp", "http://localhost:40000/mcp"],
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


def setup_environment(src_dir: Path, project_dir: Path, port: int, branch: str):
    """Create .envrc, work/ directory, git excludes, and memo file."""
    logger.info("Setting up environment...")

    # Create work/ and .vscode/
    (src_dir / "work").mkdir(exist_ok=True)
    (src_dir / ".vscode").mkdir(exist_ok=True)

    # Create .envrc
    envrc = src_dir / ".envrc"
    envrc.write_text(
        f"export PGPORT={port}\n"
        f"export PGDATA={project_dir}/data\n"
        f"export PGDATABASE=postgres\n"
        f"export PGPATH={project_dir}\n"
        f"PATH_add {project_dir}/bin\n"
        f"PATH_add {src_dir}/src/tools/pgindent\n"
    )
    _run(["direnv", "allow"], cwd=str(src_dir), check=False)

    # Set up git excludes
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

    # Create memo file
    memo_dir = project_dir / "postgres" / "work" / branch
    memo_dir.mkdir(parents=True, exist_ok=True)
    memo_file = memo_dir / f"{branch}.md"
    memo_file.touch(exist_ok=True)


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
    for i in range(60):
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", session, "-p"],
            capture_output=True, text=True,
        )
        if result.stdout:
            lines = [l for l in result.stdout.splitlines() if l.strip()]
            # Claude Code prompt: ">" or "❯" or contains input marker
            if lines and (lines[-1].startswith(">") or "❯" in lines[-1]):
                break
        time.sleep(1)

    time.sleep(2)
    subprocess.run(
        ["tmux", "send-keys", "-t", session, f"/rename {branch}", "Enter"],
        capture_output=True, text=True,
    )

    logger.info(f"tmux session '{session}' created with Claude Code running.")
    logger.info(f"  Attach: tmux attach -t {session}")


def init_branch(branch: str, base_branch: str = "master",
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
    10. Start tmux + Claude Code

    Returns the log file path.
    """
    log_path = setup_logging(log_file)
    project = branch
    project_dir = PGSQL_DIR / project

    try:
        logger.info(f"Initializing PostgreSQL environment for branch: {branch}")
        logger.info(f"Base branch: {base_branch}")

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
        setup_environment(src_dir, project_dir, port, branch)

        # 10. Initialize database
        init_database(project_dir, port)

        # 11. Setup tmux + Claude Code
        setup_tmux_claude(branch, src_dir)

        logger.info("")
        logger.info("PostgreSQL development environment setup complete!")
        logger.info(f"You can access the database with the following command:")
        logger.info(f"  {project_dir}/bin/psql -p {port} postgres")
        logger.info(f"Log file: {log_path}")

    except Exception:
        logger.exception("pg_init failed")
        raise

    return log_path
