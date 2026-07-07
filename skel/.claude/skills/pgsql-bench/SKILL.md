---
name: pgsql-bench
description: Run PostgreSQL performance benchmarks (remote via SSH by default, or local when asked). Accepts any SQL workload — INSERT, COPY, UPDATE, SELECT, etc. Generates test data, runs multi-round timing, and reports median/min/max with speedup ratios.
allowed-tools: Bash, Write, Read
---

# PostgreSQL Performance Benchmark Skill

Run timing tests for any PostgreSQL workload, across parameter variants (e.g. parallelism levels, batch sizes, config knobs). **Runs on the remote server via SSH by default**; run locally only when the user explicitly asks for it.

## Invocation examples

- `/pgsql-bench` — benchmark current workload on the default remote server (`shinya@192.168.1.3`)
- `/pgsql-bench local` — run on this machine instead of the remote server
- `/pgsql-bench remote=192.168.1.5` — run on a different remote host
- `/pgsql-bench remote=shinya@192.168.1.3 rounds=7` — custom user and rounds
- `/pgsql-bench variants="PARALLEL 0, PARALLEL 2, PARALLEL 4"` — explicit variant list
- `/pgsql-bench local pgbin=/home/shinya/pgsql/inst/bin pgdata=/home/shinya/pgsql/data` — local run with custom PostgreSQL paths

## Parameters (all optional)

| Parameter | Default | Description |
| --- | --- | --- |
| `remote=<[user@]host>` | `shinya@192.168.1.3` | SSH target; user defaults to `shinya`. Runs remotely unless `local` is given |
| `local` | (off) | Flag: run on this machine instead of the remote server. Overrides `remote` |
| `pgbin=<path>` | auto-detect | Directory containing `psql`, `pg_ctl`, etc. |
| `pgdata=<path>` | auto-detect | PostgreSQL data directory |
| `db=<name>` | `bench` | Database to use |
| `rounds=<n>` | `5` | Timing rounds per variant |
| `variants=<list>` | (ask user or infer) | Comma-separated labels for each variant; drive the SQL in Step 3 |
| `tmpdir=<path>` | `/tmp` | Working directory for generated files |

## Execution procedure

### Step 1 — understand the workload

Before doing anything, **clarify what to benchmark** unless it is already obvious from the conversation:

- What SQL operation? (INSERT, COPY FROM, UPDATE, SELECT, DDL, …)
- What is varying across variants? (parallelism, batch size, index presence, GUC value, …)
- How large should the test data be? (row count, data types, file size)
- Does the workload need special schema or data setup?

Summarize the plan in one short paragraph before writing any scripts.

### Step 2 — resolve target environment

**Default to remote.** Unless the user passes `local`, run the benchmark on the remote server: use the `remote` target (default `shinya@192.168.1.3`) and prefix all commands — psql, pg_ctl, data generation, the timing script — with `ssh <host>`. Verify connectivity first (`ssh <host> echo ok`); if it fails, report the error and stop (see Error handling) rather than falling back to local.

Run locally only when the user explicitly asks (the `local` flag, or an equivalent request like "run it here" / "ローカルで"). In that case, execute the commands directly with no `ssh` prefix. When `local` and `remote` are both somehow present, `local` wins.

The `pgbin`, `pgdata`, `db`, and `tmpdir` paths below all resolve **on whichever machine runs the benchmark** — the remote host by default. Auto-detect them on the target (i.e. through `ssh <host>` when remote).

Auto-detect `pgbin` in order: `dirname $(which psql)`, `~/pgsql/inst/bin`, `/usr/pgsql-*/bin`, `/usr/lib/postgresql/*/bin`. Auto-detect `pgdata` from `$PGDATA` env, then `~/pgsql/data`.

If PostgreSQL is not running, start it: `pg_ctl -D $pgdata -l /tmp/pg_bench.log start` and stop it after the benchmark.

Create the database if missing: `createdb $db 2>/dev/null || true`.

Note the following environment facts in the report header:
- CPU model and count (`lscpu | grep 'Model name\|^CPU(s)'`)
- RAM (`free -h | head -2`)
- PostgreSQL version (`psql -d $db -tAc 'SELECT version()'`)
- Relevant GUC values for the workload (e.g. `shared_buffers`, `max_worker_processes`)

### Step 3 — set up schema and data

Write setup scripts to `$tmpdir/bench_setup.sh` (or `.py` if data generation needs Python) and execute them on the target.

**Schema**: Create tables with `DROP TABLE IF EXISTS … ; CREATE TABLE …` so runs are repeatable.

**Data**: Generate realistic test data appropriate for the workload. Python (`python3`) is available for data generation. Write generated files to `$tmpdir/bench_*.csv` or similar. For COPY benchmarks, use `|` as delimiter with a header row.

**Volume**: Scale to something that makes each serial run take at least 0.5 s — enough to distinguish variants but not so large that setup dominates. Aim for 1–30 s per serial run.

### Step 4 — write and run the timing script

Write `$tmpdir/bench_run.sh`. Structure:

```
for each VARIANT:
  for each ROUND 1..N:
    reset state (TRUNCATE, DROP INDEX, SET GUC, …)
    record start_ms = date +%s%3N
    execute the workload SQL via psql -d $db -c "..."
    record end_ms = date +%s%3N
    verify correctness (row count, expected result, …)
    print:  "VARIANT=$label ROUND=$r TIME=$((end-start)) ROWS=$cnt"

  compute and print: VARIANT=$label MEDIAN=$m MIN=$min MAX=$max
```

Correctness check: after each run, verify that the operation produced the expected result (row count, checksum, output value). If the check fails, print `WARN: unexpected result` and skip that data point rather than silently including wrong numbers.

Execute the script on the target and stream its output.

### Step 5 — parse output and report

Parse the `VARIANT=… MEDIAN=… MIN=… MAX=…` lines from the script output.

**Summary table** — one row per variant, median time, speedup vs. the baseline (first variant or the one labeled `serial`/`par=0`), and stability range:

```
Benchmark: COPY FROM with varying PARALLEL degree
Host: home0102 (Intel i5-1135G7, 8 cores) | PostgreSQL 19devel | shared_buffers=2GB
Dataset: 3 000 000 rows × 4 columns (133 MB)

| Variant    | Median  | Speedup | Range (min–max)   |
| Serial     | 1831 ms |  1.00x  | 1747–2070 ms      |
| PARALLEL 2 | 1004 ms |  1.82x  |  881–1092 ms      |
| PARALLEL 4 |  688 ms |  2.66x  |  524–728 ms       |
| PARALLEL 8 |  702 ms |  2.61x  |  482–709 ms       |
```

**Stability note**: if max/min ratio > 1.5 for any variant, flag it and suggest increasing `rounds` or checking for background interference.

**Analysis**: For each variant, explain *why* the timing changed (or didn't) — reference the specific bottleneck (CPU, WAL locks, I/O, lock contention, memory pressure, …). Keep it to 2–3 sentences per variant.

**Recommendation**: State the optimal variant and the expected real-world benefit.

## Reusable patterns

### COPY FROM with PARALLEL option

```sql
-- serial
COPY t FROM '/tmp/data.csv' WITH (DELIMITER '|', HEADER);
-- parallel
COPY t FROM '/tmp/data.csv' WITH (PARALLEL 4, DELIMITER '|', HEADER);
```

Reset between runs: `TRUNCATE t;`

### INSERT with varying batch size

```sql
INSERT INTO t SELECT ... FROM generate_series(1, $n);
```

Reset between runs: `TRUNCATE t;`

### Index creation variants

```sql
CREATE INDEX ON t (col);          -- default
CREATE INDEX ON t (col) WITH (deduplicate_items=off);
```

Reset between runs: `DROP INDEX IF EXISTS …`

### GUC knob sweep

```sql
SET work_mem = '64MB'; <query>;
SET work_mem = '256MB'; <query>;
```

No reset needed if within the same session; use `psql -c "SET …" -c "<query>"`.

## Error handling

- **Silent failure**: compare actual row count / result against expected; warn and skip if wrong
- **Outlier detection**: if one round is > 3× the median, note it in the range but do not discard it — let the user decide
- **pgbin not found**: ask the user explicitly rather than guessing further
- **SSH failure**: report the error and stop; do not attempt to fall back to local silently
