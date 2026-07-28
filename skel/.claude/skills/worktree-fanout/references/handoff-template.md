# Handoff prompt template

One file per work item. The reader has **zero context**: no report, no
conversation, no way to ask. Write for someone competent who has never seen
this problem.

Write in the language the user is working in. Keep code identifiers, file
paths, and quoted error messages verbatim.

---

## Required sections

### `# 引き継ぎ: <一行で何を直す/作るか>`

Title names the defect or feature, not the ticket number.

### `## 依頼`

What you want produced, and permission to trust the findings below without
redoing them — with the standing exception that the child must still validate
the fix direction itself. One short paragraph.

> PostgreSQL master のバグを 1 件修正し、pgsql-hackers に投げられる形のパッチにしてほしい。
> バグは実機で再現確認済み。以下は前のセッションの調査結果なので、再調査せずここから
> 始めてよい (ただし修正方針は自分で妥当性を確認すること)。

### `## 環境`

Only what changes what the child types:

- `.envrc` (direnv) sets `PGPORT`/`PGDATA`/`PATH`, so plain `psql -d postgres`
  reaches this worktree's server. Assert-enabled, `-O0`.
- Scratch goes in `work/tmp/`, not `/tmp`. Do not set `TMPDIR` (TAP's 107-char
  socket path limit breaks `make check`).
- Configured **without** `--enable-depend`: changing a header requires a full
  `make clean` rebuild. **Say whether this item touches headers** — it changes
  how the child sequences its work.
- Whether the repro needs two sessions, two clusters, or `wal_level=logical`.

### `## 基準コミット`

Non-negotiable. `pg_init` syncs the fork, so the child's HEAD may be newer than
what you verified against.

> このドキュメント中のファイル名:行番号は master の `<sha>` 時点で実ファイルと照合済み。
> worktree の HEAD がこれより新しい場合は行番号がずれている可能性があるので、行番号ではなく
> **関数名で探すこと**。ずれていた場合は、まず該当コミットで挙動が変わっていないか確認してから
> 着手すること (既に誰かが直している可能性がある)。

### `## バグの内容` (features: `## 作るもの`)

Three subsections:

- **症状** — observable behavior, in terms a user would notice.
- **根本原因** — the mechanism, citing `file:line`. Quote the 3-5 offending
  lines. Explain *why* the code is wrong, not just where it is.
- **ドキュメントとの矛盾 / 経緯 / 到達性** — as applicable. Which doc sentence
  it contradicts. Which commit introduced it and what that commit's author
  believed. What privileges an attacker needs.

### `## 再現`

Self-contained SQL a child can paste with no edits: role creation, grants,
`SET SESSION AUTHORIZATION`, cleanup. Then, in a separate block, the **exact
observed output** — not a paraphrase — and the expected output.

Include the control experiments that pinned the mechanism. They are what stops
the child from re-litigating whether the bug is real, and what they will
re-run after the fix.

Multi-session repros: label `[A]` / `[B]` and say what blocks where.

### `## 修正方針 (要検証)`

The `(要検証)` is load-bearing. Give the direction and the specific edits, then
explicitly invite disagreement. If two shapes are viable, give both and say the
child may choose. If you know a tempting approach is wrong, say why — that
saves the most time of anything in the file.

### `## 完了条件`

A checklist, concrete enough to be checkable:

- Regression test **and where it belongs** (`src/test/regress/sql/<file>.sql`,
  `src/test/isolation` when it needs two sessions, a specific TAP file and the
  existing block to model it on).
- Which suites must pass.
- Whether existing expected output may legitimately change, and the obligation
  to explain it if so.
- Produce the patch with the `commit` skill + `git format-patch`.
- Decide and state the backpatch range.

### `## 報告先`

Where the child stops. Always forbid sending mail. For security findings, say
security@postgresql.org explicitly and that the public list is off limits.

---

## Escalation

Name the decisions the child should bring back instead of deciding alone: ABI
changes on back branches, overlap with work already in flight, anything that
widens the patch's scope. A prompt that says "if unsure, ask me" for the two or
three genuinely contested points produces better patches than one that pretends
everything is settled.
