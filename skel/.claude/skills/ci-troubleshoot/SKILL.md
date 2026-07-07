---
name: ci-troubleshoot
description: >-
  Troubleshoot a failing GitHub Actions CI run: find which job/test failed and
  why by drilling from the check-runs summary into job logs and, crucially, the
  uploaded artifact logs (the real per-test detail). Use whenever CI is red, a
  platform-specific job fails (Windows/macOS/MinGW), the user pastes a GitHub
  commit / PR / Actions URL and asks what broke, or says "CIが失敗", "なぜCIが落ちた",
  "Windowsで失敗", "debug the CI", "why is CI failing". Has dedicated support for
  PostgreSQL's meson + TAP CI (see references/postgres-ci.md).
---

# GitHub CI Troubleshooting

Find the root cause of a red GitHub Actions run by drilling down a funnel:

```
check-runs (which jobs failed)
  → job log    (which step/test failed, summary line)
    → annotations (usually generic — skip if unhelpful)
    → ARTIFACT logs (the real detail: per-test TAP + per-node server logs)
      → root cause → fix
```

The single most important lesson: **the actionable failure detail is almost
always in the uploaded artifacts, NOT in the job log.** The job log only tells
you *which* test died; the artifact tells you *why*.

## Step 0 — Get the target (owner/repo + commit SHA)

From a pasted URL or the local checkout:

- Commit URL `github.com/OWNER/REPO/commit/SHA` → use directly.
- PR URL/number → `gh pr view N --repo OWNER/REPO --json headRefOid -q .headRefOid` for the SHA, or `gh pr checks N --repo OWNER/REPO` for a quick pass/fail table.
- Local branch → `git remote -v` for OWNER/REPO, `git rev-parse HEAD` for the SHA (confirm it was actually pushed).

`OWNER/REPO` for the rest of this doc is e.g. `shinyaaa/postgres`.

## Step 1 — Which jobs failed?

```bash
gh api repos/OWNER/REPO/commits/SHA/check-runs \
  --jq '.check_runs[] | "\(.conclusion)\t\(.name)\t\(.id)\t\(.details_url)"'
```

Note each failed job's **name** and **id**. Read the *pattern* of pass/fail —
it often localizes the cause before you read a single log:

- Linux passes, Windows/macOS fails → platform-specific (paths, line endings, timing, shutdown, locale, case-sensitivity).
- One test slice fails, the sibling slice passes → a specific *test*, not a compile error (a compile break fails every job).
- "CompilerWarnings" fails alone → a warning, not a test.
- Everything fails the same way → compile/setup/infra, look at the earliest job.

## Step 2 — Read the failed job log (find the failing test)

The `gh api .../logs` endpoint and large outputs can choke the harness
(`undefined is not an object (evaluating 'H.includes')`) — **always write logs
to a file and grep the file; never dump a full log inline.** Use curl with the
gh token, which is the most reliable. Keep all scratch in the repo-local
`work/tmp/` (gitignored), never `/tmp` — create it once with `mkdir -p work/tmp`:

```bash
mkdir -p work/tmp
TOK=$(gh auth token)
curl -sL -H "Authorization: Bearer $TOK" \
  "https://api.github.com/repos/OWNER/REPO/actions/jobs/JOB_ID/logs" \
  -o work/tmp/job.log
# then grep for the failure, filtering out PATH/env noise:
grep -anE "FAIL|not ok|ERROR|Bail out|does not shut down|Tests=|exit (status|code)" work/tmp/job.log \
  | grep -viE "Program Files|hostedtoolcache|chocolatey|Visual Studio" | head -40
```

If a transient `H.includes` harness error fires, just retry — it is
intermittent. Keep output small (grep, `head`, `wc`), write big things to files.

This identifies the failing test/step (e.g. a meson line:
`191/197 test_misc - .../014_log_vacuum_blockers   ERROR   (exit status 255)`).
Check-run **annotations** (`gh api repos/OWNER/REPO/check-runs/CHECK_RUN_ID/annotations`)
are usually just "Process completed with exit code 1" — note them but don't rely on them.

## Step 3 — Download the artifact logs (the real detail)

This is where the actual TAP output, regress logs, and per-node server logs
live. List artifacts for the run, download the zip, extract just what you need:

```bash
RUN_ID=...   # from the details_url: /actions/runs/RUN_ID/job/JOB_ID
gh api repos/OWNER/REPO/actions/runs/RUN_ID/artifacts \
  --jq '.artifacts[] | "\(.id)\t\(.name)"'

TOK=$(gh auth token)
curl -sL -H "Authorization: Bearer $TOK" \
  "https://api.github.com/repos/OWNER/REPO/actions/artifacts/ARTIFACT_ID/zip" \
  -o work/tmp/art.zip
unzip -l work/tmp/art.zip | grep -iE "FAILING_TEST_NAME"     # find the right paths
unzip -o -q work/tmp/art.zip "path/to/FAILING_TEST/log/*" -d work/tmp/cilogs
```

Then read the per-test logs (Step 4). For PostgreSQL's exact artifact layout and
log filenames, read `references/postgres-ci.md`.

## Step 4 — Root-cause from the detailed logs

Read two things and correlate timestamps between them:

1. **The test driver / TAP log** — shows which assertion or phase failed, and
   the exact command that errored (e.g. `Bail out! pg_ctl stop failed`).
2. **The server / app log** — shows what the program actually did
   (crash, slow checkpoint, FATAL, timeout) at that moment.

Correlating the two usually pins the cause — and beware your first theory. A
real session took **three** tries because each fix shipped on a guess instead of
on the logs:

1. TAP said `pg_ctl stop failed`; a ~11 s gap before `database system is shut
   down` looked like a slow shutdown checkpoint → `stop('immediate')`. Re-run
   failed **identically** — `immediate` skips the checkpoint, disproving it.
2. Next guess: a streaming standby's walreceiver blocked in a socket read →
   `$node->kill9`. But the *primary's* log showed the walsender hit
   `unexpected EOF` and released the slot in ~7 ms — the disconnect was instant,
   so that was wrong too (and `kill9` is unproven on Windows + orphans children).
3. Only then: re-read the *server* log properly. It DID log `database system is
   shut down` (just ~10 s late, the postmaster's child-kill escalation). So the
   server stopped fine and **pg_ctl's failure was spurious** — tolerate it with
   `$node->stop('fast', fail_ok => 1)`.

Takeaways: **a fix that fails the same way disproves your diagnosis — re-diagnose,
don't re-skin it.** And **don't trust a tool's "failed" over the program's own
log** — pg_ctl said "does not shut down" while the postmaster logged that it had.
Verify each fix actually changed the failure mode before claiming it works.

Before proposing a fix, decide **whose bug it is**:

- A real code bug the platform exposes (uninitialized memory, races, 64-bit
  assumptions, path/encoding handling) → fix the code.
- A test-harness fragility (timing, shutdown races, ordering, platform
  assumptions in the test) → fix the test.
- Always state whether the failure pre-existed your changes (check whether the
  failing commit is before/after your work) and whether your pending changes
  even touch the failing path — don't claim a fix you can't connect to the
  cause.

## Step 5 — Verify and report

- Run the affected test locally if the platform allows; otherwise say so
  explicitly. You usually cannot run Windows/macOS locally — be honest that the
  fix is reasoned from the logs + a known pattern, and that re-running CI is the
  real confirmation.
- Report: which job(s) failed, the one-line root cause, the fix, and how it was
  (or could not be) verified. If multiple failed jobs share one cause, say so.

## Reference

- `references/postgres-ci.md` — PostgreSQL's GitHub Actions matrix, the artifact
  log layout (`build/testrun/...`), TAP/meson output anatomy, and a catalog of
  known platform-specific failure patterns with their fixes.
