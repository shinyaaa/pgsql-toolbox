---
name: worktree-fanout
description: >-
  Take a set of independent work items already identified in this session —
  bugs from a bug hunt, features from a brainstorm, review findings, a
  migration's call sites — and give each one its own worktree, its own
  PostgreSQL build, and its own Claude Code session primed with a
  self-contained handoff prompt. Use whenever the user wants several findings
  worked on in parallel rather than one at a time: "それぞれを別worktreeで実装して",
  "別々のworktreeで直して", "各バグをworktreeに分けて", "引き継ぎプロンプトを作って",
  "fan these out into worktrees", "one worktree per bug", "spawn a session for
  each". Also trigger right after a bug sweep or feature brainstorm produces a
  numbered list and the user asks to start working on them.
---

# Worktree fan-out

Turn N identified work items into N working sessions. Each gets a `pg_init`
worktree (own port, own build, own cluster) and a Claude Code session that
starts from a handoff prompt written for a reader with **zero context**.

The handoff prompt is the whole product. The child session cannot see this
conversation, cannot see the report, and cannot ask what you meant. Everything
it needs goes in the file.

## Workflow

1. **Fix the item list.** Confirm the exact set with the user before building
   anything — N worktrees means N full builds, N clusters, N agent sessions.
   Show the branch names and what each covers, and let the user cut the list.
2. **Verify every code reference.** Before writing a single prompt, check each
   `file:line` you are about to cite against the real file (`sed -n "${l}p"`).
   A prompt that sends the reader to the wrong line costs more than it saves.
3. **Write one handoff file per item** into
   `work/<current-branch>/handoff/NN-<slug>.md`, plus a `README.md` index.
   Follow `references/handoff-template.md`.
4. **Pilot one.** Run the spawn script for a single branch. Confirm the
   worktree built, the handoff landed at `work/<branch>/<branch>.md`, and the
   session actually read it and started.
5. **Spawn the rest** in the background, serially.
6. **Verify each session** is on the right task (see Verifying below).

## Branch names

Match the repo's existing convention: `fix-*` for bugs, `feat-*` for features,
`poc-*` for experiments, `rev-*` for reviews of someone else's patch. Name the
subject, not the fix: `fix-rls-drop-owned-policy`, not `fix-policy-bug-4`.

## Handing the prompt over

Do **not** paste the markdown into the session with `tmux send-keys`. Multi-KB
multi-line text submits at every newline and arrives shredded.

`pg_init` creates `work/<branch>/<branch>.md` as an empty memo file. Overwrite
it with the handoff, then send one single-line prompt:

```
work/<branch>/<branch>.md に作業指示が入っています。読んで、その内容に従って作業を開始してください。
```

The content reaches the model verbatim and nothing depends on TUI paste
behavior.

## Running it

`scripts/spawn-worktrees.sh <handoff-dir> [branch ...]` reads
`<handoff-dir>/manifest.tsv` (`branch<TAB>handoff-file` per line) and for each
branch runs `pg_init -b`, copies the handoff into place, and sends the prompt.
With branch names as extra args it processes only those — that is how you pilot
one before committing to the rest.

**Serial, always.** `pg_init` runs `make -s world -j$(nproc)`. Running two at
once thrashes. Budget about 2 minutes per worktree on a 12-core box.

Run the full batch with `run_in_background`, then wait with an until-loop on
`pgrep -f spawn-worktrees.sh` rather than polling by hand.

### Preflight

- Disk: about 600MB per worktree.
- `pg_init` runs `gh repo sync` and branches from current master, so the base
  commit may be newer than the one you verified line numbers against. Record
  the commit you verified in every prompt (see the template) — do not skip
  this, it is the difference between "line 648" being helpful and misleading.

## Verifying after spawn

Claude Code redraws over the alternate screen, so `tmux capture-pane -S -`
does **not** reliably contain the prompt you sent. Grepping scrollback for it
gives false negatives. Instead check the *visible* pane for evidence the
session is on the right task:

```bash
tmux capture-pane -t "$branch" -p | grep -v "^\s*$" | tail -14
```

Look for it touching the files the handoff named. Report any session that is
idle, stuck on a permission dialog, or working on the wrong thing.

## Scope control for the children

Every handoff must state where the child stops. Default: **produce the patch
and stop.** Do not let child sessions send mail — a fan-out of 8 sessions each
deciding to post to pgsql-hackers is the failure mode to design against.

For security-sensitive findings (privilege escalation, RLS/ACL bypass,
information disclosure), say so explicitly in the prompt: the patch goes to
security@postgresql.org privately, not to the public list, and the child does
not draft the mail.

Flag in the prompt when items collide — two branches editing the same function,
or several needing `make clean` full rebuilds at once — so the user can
sequence them.
