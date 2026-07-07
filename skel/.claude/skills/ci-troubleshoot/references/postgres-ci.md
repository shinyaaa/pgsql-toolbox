# PostgreSQL GitHub Actions CI — log layout & known failures

PostgreSQL's CI is defined in `.github/workflows/ci.yml` (plus the older
`.cirrus*.yml`). Builds use **meson + ninja**; functional tests are **pg_regress**
and **TAP (`prove`/`Test::More`)**.

## Job matrix (check-run names)

Typical names seen on `check-runs` (exact set evolves):

- `SanityCheck`, `CompilerWarnings`
- `Linux - Meson (64-bit)`, `Linux - Meson (32-bit)`, `Linux - Autoconf`
- `macOS - Meson`
- `Windows - Visual Studio - Slice 1/2`, `Windows - Visual Studio - Slice 2/2`
- `Windows - MinGW - Meson`

Triage hints:
- **Slices** split the test suite. A failure in *one* VS slice but not the other
  ⇒ a specific failing test, not a build break (a build break fails all jobs).
- VS and MinGW failing the **same** test ⇒ one Windows-platform cause; one fix
  covers both. Always confirm both, don't assume.
- Relevant env on Windows jobs: `PGCTLTIMEOUT=120`, `TEST_JOBS=4`,
  `PG_TEST_USE_UNIX_SOCKETS=1`, ASAN/UBSAN halt-on-error, cassert + injection
  points enabled.

## Reading the job log (meson output)

`MTEST_ARGS` includes `--print-errorlogs`, so failing tests *may* print their
logs inline — but **teardown failures (e.g. a node that won't stop) often do
NOT**, so don't trust the absence of detail in the job log. The meson summary
near the end is the anchor:

```
NNN/MMM test_misc - postgresql:test_misc/014_log_vacuum_blockers   ERROR   25.10s   (exit status 255 or 0xff)
...
Ok:  180   Fail:  1   Skipped:  16
Full log written to D:\...\build\meson-logs\testlog.txt
```

`(exit status 255)` with **all subtests passing** ⇒ the failure is in
setup/teardown (node start/stop), not an assertion.

## Artifact log layout (where the real detail is)

The job uploads an artifact (e.g. `logs-windows-vs-<runid>-1`) globbing
`**/*.log`, `**/*.diffs`, `**/regress_log_*`, `**/crashlog-*.txt`,
`build/meson-logs/**`, `**/config.log`. After `unzip`, the per-test logs are:

```
build/testrun/<group>/<test>/log/
    regress_log_<test>            # TAP driver output: ok/not ok, "Bail out!", commands run
    <test>_main.log              # server log of the default node ("main")
    <test>_<nodename>.log        # server log of each *named* node (standbys, etc.)
build/meson-logs/testlog.txt     # the full meson test log (all tests)
src/test/regress/regression.diffs  # pg_regress expected-vs-actual diff, if a SQL test failed
```

Root-cause by correlating **timestamps** between `regress_log_<test>` (what the
test did / which step failed) and `<test>_<node>.log` (what that server did).

Useful greps once extracted:
```bash
grep -nE "not ok|Bail out|# Running|pg_ctl|timed out" .../log/regress_log_<test>
grep -nE "PANIC|FATAL|ERROR|received .* shutdown|checkpoint|shut down|terminat" .../log/<test>_*.log
```

## Known platform-specific failure patterns

### "server does not shut down" / "pg_ctl stop failed" (Windows)
TAP shows `Bail out!  pg_ctl stop failed` (`pg_ctl stop failed: 256`, test exits
255), usually followed by `Stale postmaster.pid file ... PID NNNN no longer
exists`. **First decide whether the server actually failed to stop, or pg_ctl
just mis-reported it** — read the culprit node's *server* log:

- If it logged `database system is shut down` (just slowly — a long gap after
  `received ... shutdown request`, often a near-constant ~10 s), the server DID
  stop and pg_ctl raced its exit. The failure is **spurious**.
- If there is no such line, it genuinely hung — different problem.

The ~10 s gap is the postmaster's immediate/abort child-kill escalation
(`SIGKILL_CHILDREN_AFTER_SECS = 5`, applied twice): one child does not act on
the shutdown signal until force-terminated. On Windows a streaming standby is a
common trigger; comparing nodes, a sibling standby stops in milliseconds while
the affected one takes ~10 s. Note the disconnect itself is *fast* — the primary
walsender logs `unexpected EOF on standby connection` / `released ... slot`
almost immediately, so any "slot went inactive" check still passes.

**Fix (spurious case):** tolerate the bogus pg_ctl result with
`$node->stop('fast', fail_ok => 1)`. `stop` then calls `_update_pid(-1)`, sees
the stale pidfile whose PID is gone, and correctly marks the node down — no
bail, no orphans, and Linux is unaffected (there `stop` succeeds, so `fail_ok`
never triggers). Do **not** reach for `$node->kill9` here: it is used by exactly
one suite test (`017_shm.pl`, which is `skip_all` on Windows) so it is unproven
on Windows, and it only TerminateProcess-es the *postmaster* — children are
orphaned (no tree-kill on Windows), risking the file-handle-lingering problems
Windows tests already fight. `stop(..., fail_ok => 1)` lets the server shut down
normally and only ignores pg_ctl's verdict.

Lesson (learned the hard way, three wrong fixes): the *diagnosis* drove the fix,
and the first diagnoses were wrong. "slow checkpoint" (→`immediate`) failed
identically because `immediate` skips the checkpoint; "blocked walreceiver"
(→`kill9`) was wrong because the primary log proved the disconnect was instant.
Only reading the server log — *did it say "shut down"?* — revealed pg_ctl's
failure was spurious. **When a CI fix fails the same way, your diagnosis is
wrong; re-read the logs, don't re-skin the fix. And don't trust a tool's
"failed" exit over what the program's own log says it did.**

### Replication / hot-standby-feedback flakiness (any platform, surfaces on slow CI)
Tests that DELETE then expect tuples to stay "recently dead" can race the
feedback/xmin advancing. Poll for the **specific** xmin to be reflected
(`backend_xmin = '<captured>'::xid`, or the slot's `xmin =`), not merely
`IS NOT NULL`; remember `query_until(qr//, ...)` returns *immediately*. For a
disconnected-slot check, create a fresh dead tuple *after* disconnect so its
xid is newer than the (possibly advanced) frozen slot xmin.

### GUC unit gotcha
Time/size GUCs apply their base unit before rounding. `wal_receiver_status_interval
= 100ms` rounds to **0** (unit is seconds) which *disables* feedback; use whole
seconds (`1s`). Check the GUC's `flags => 'GUC_UNIT_*'` in
`src/backend/utils/misc/guc_parameters.dat`, and verify with
`postgres -C <guc> -D <datadir>`.

### Other Windows/macOS classics
- Path separators (`D:\...` vs `/`), case-insensitive FS, CRLF in expected files.
- Background `psql` sessions terminated mid-test can leave lingering file
  handles on Windows (breaks a later node start/stop) — `->quit` them, or order
  node setup before such sessions.
- Locale/collation differences in `regression.diffs` (macOS/ICU).
- Timeouts (slow runners): prefer `poll_query_until` over fixed sleeps.

## Quick command cheatsheet

```bash
mkdir -p work/tmp   # repo-local scratch (gitignored); use it instead of /tmp

# pass/fail table for a PR
gh pr checks N --repo OWNER/REPO

# failed jobs for a commit (name + id + run url)
gh api repos/OWNER/REPO/commits/SHA/check-runs \
  --jq '.check_runs[]|select(.conclusion=="failure")|"\(.name)\t\(.id)\t\(.details_url)"'

# a job's full text log (write to file, then grep)
TOK=$(gh auth token)
curl -sL -H "Authorization: Bearer $TOK" \
  https://api.github.com/repos/OWNER/REPO/actions/jobs/JOB_ID/logs -o work/tmp/job.log

# artifacts for the run, then download + extract the failing test's logs
gh api repos/OWNER/REPO/actions/runs/RUN_ID/artifacts --jq '.artifacts[]|"\(.id)\t\(.name)"'
curl -sL -H "Authorization: Bearer $TOK" \
  https://api.github.com/repos/OWNER/REPO/actions/artifacts/ARTIFACT_ID/zip -o work/tmp/art.zip
unzip -o -q work/tmp/art.zip "build/testrun/*/<test>/log/*" -d work/tmp/cilogs
```

Note: `RUN_ID` and `JOB_ID` both appear in a job's `details_url`
(`/actions/runs/RUN_ID/job/JOB_ID`).
