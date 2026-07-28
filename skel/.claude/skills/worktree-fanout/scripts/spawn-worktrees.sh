#!/bin/bash
# Fan work items out into one worktree + Claude Code session each.
#
#   spawn-worktrees.sh <handoff-dir> [branch ...]
#
# <handoff-dir>/manifest.tsv holds one "branch<TAB>handoff-file" per line.
# With branch names as extra args, only those are processed (use this to pilot
# one before committing to the whole batch).
#
# Serial by design: pg_init runs `make -s world -j$(nproc)`.

set -u

HANDOFF_DIR="${1:-}"
if [ -z "$HANDOFF_DIR" ] || [ ! -f "$HANDOFF_DIR/manifest.tsv" ]; then
  echo "usage: $0 <handoff-dir> [branch ...]   (needs <handoff-dir>/manifest.tsv)" >&2
  exit 1
fi
shift

TOOLBOX="${PGSQL_TOOLBOX:-$HOME/git/pgsql-toolbox}"
PGROOT="${PGSQL_WORKTREE_ROOT:-$HOME/pgsql}"
LOG="$HANDOFF_DIR/spawn.log"

if [ ! -x "$TOOLBOX/bin/pg_init" ]; then
  echo "pg_init not found at $TOOLBOX/bin/pg_init (set PGSQL_TOOLBOX)" >&2
  exit 1
fi

echo "=== start $(date -Is) ===" >> "$LOG"

while IFS=$'\t' read -r branch md; do
  case "$branch" in ''|\#*) continue ;; esac

  if [ $# -gt 0 ]; then
    match=0
    for want in "$@"; do [ "$want" = "$branch" ] && match=1; done
    [ $match -eq 1 ] || continue
  fi

  if [ ! -f "$HANDOFF_DIR/$md" ]; then
    echo "### [$branch] FAILED: handoff file '$md' not found" >> "$LOG"
    continue
  fi

  echo "### [$branch] pg_init start $(date -Is)" >> "$LOG"
  if ! "$TOOLBOX/bin/pg_init" -b "$branch" >> "$LOG" 2>&1; then
    echo "### [$branch] FAILED pg_init" >> "$LOG"
    continue
  fi

  src="$PGROOT/$branch/postgres"
  if [ ! -d "$src" ]; then
    echo "### [$branch] FAILED: worktree dir missing at $src" >> "$LOG"
    continue
  fi

  # pg_init leaves work/<branch>/<branch>.md as an empty memo; fill it in.
  mkdir -p "$src/work/$branch"
  cp "$HANDOFF_DIR/$md" "$src/work/$branch/$branch.md"
  echo "### [$branch] handoff copied" >> "$LOG"

  # One single-line prompt pointing at the file. Never paste the markdown
  # itself: send-keys submits at every newline and it arrives shredded.
  if tmux has-session -t "$branch" 2>/dev/null; then
    sleep 3
    tmux send-keys -t "$branch" -l \
      "work/$branch/$branch.md に作業指示が入っています。読んで、その内容に従って作業を開始してください。"
    sleep 1
    tmux send-keys -t "$branch" Enter
    echo "### [$branch] prompt sent" >> "$LOG"
  else
    echo "### [$branch] WARNING: no tmux session, prompt not sent" >> "$LOG"
  fi

  echo "### [$branch] done $(date -Is)" >> "$LOG"
done < "$HANDOFF_DIR/manifest.tsv"

echo "=== all done $(date -Is) ===" >> "$LOG"
