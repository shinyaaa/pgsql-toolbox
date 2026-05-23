# pgsql-hackers conventions

Mechanics and etiquette the community expects. These are not stylistic
preferences — getting them wrong gets the email ignored or corrected on-list.

## Format

- **Plain text only.** No HTML mail. No rich formatting, no inline images
  (attach images/charts as files and refer to them, e.g. "see the attached
  chart.png").
- **Do not hard-wrap paragraphs in the draft you produce** — the user's mail
  client wraps them. Keep blank lines between paragraphs/list-items/sections, and
  preserve the internal line structure of code/SQL/log blocks and the signature.
- **Patches are attached**, generated with `git format-patch` (one file per
  commit, e.g. `v2-0001-...patch`, `v2-0002-...patch`). Name the series version
  consistently (v1, v2, …). The email refers to them by number ("the 0001 patch").
- **Subject line** = a concise, imperative description of the change, matching
  PostgreSQL commit-message style: "Add mode column to pg_stat_progress_vacuum",
  "Report oldest xmin source when autovacuum cannot remove tuples". For replies,
  the mail client prepends "Re: " — don't type it yourself unless writing the raw
  subject.

## Quoting / posting style

- **Bottom-post and interleave.** Reply *below* the quoted text, trimmed to the
  part you're answering. Never top-post. The user has stated this preference
  on-list and pointed others to
  https://wiki.postgresql.org/wiki/Mailing_Lists#Email_etiquette_mechanics.
- **Trim quotes** to the minimum needed for context. Don't quote an entire
  message just to add one line at the bottom.
- **Attribution line** precedes a quote: `On <date>, <Name> <addr> wrote:`.

## Citations

- **Threads/messages:** `https://www.postgresql.org/message-id/<message-id>` or the
  shortform `https://postgr.es/m/<message-id>`.
- **Commits:** refer inline by short hash, e.g. "commit dc9f8a798". Optionally link
  to `https://git.postgresql.org/gitweb/?p=postgresql.git;a=commit;h=<hash>`.
- **Commitfest entry:** `https://commitfest.postgresql.org/<NN>/<NNNN>/`. New
  features should get a commitfest entry; it's normal to mention it.
- Number footnotes `[1]`, `[2]`, … in first-mention order and list them at the
  bottom, just above the signature.

## What committers reward (and look for)

Distilled from committer proposals (Nathan Bossart, Melanie Plageman, Peter
Eisentraut — see [examples.md](examples.md) for the annotated originals):

1. **Motivation first.** State the problem and why current behavior is
   insufficient before the solution. Reviewers triage by motivation.
2. **Show the alternatives you considered and why you rejected them.** This
   pre-empts the first round of review questions.
3. **Numbers for performance claims.** Paste real before/after output — vacuum
   durations, WAL volume, buffer usage, P99 latency, a summary table. Note the
   benchmark setup honestly (e.g. "compressed timelines", extra patches applied).
4. **Per-patch breakdown for a series.** Say what each numbered patch does, which
   are preliminary/refactoring/WIP, and which are optional or should be discussed
   first.
5. **Honest status.** PoC / WIP / v1 / ready-for-committer. Flag known gaps and
   list remaining TODOs explicitly — reviewers respect this and it directs their
   attention.
6. **Precise prior-art citations.** Commits by hash, threads by message-id,
   commitfest entry. Credit people whose ideas/feedback shaped the design
   ("built on suggestions from Robert and Andres").
7. **Match length to the change.** A one-line fix gets a few sentences ("Proposed
   patch attached."); a major feature gets the full treatment. Don't pad a small
   change with ceremony, and don't under-explain a big one.

## Common pitfalls to avoid

- Marketing tone, superlatives, exclamation marks in the argument.
- Asserting a benefit without a concrete example or number.
- Proposing user-facing syntax without checking/citing how other RDBMS do it.
- Forgetting the commitfest entry for a new feature.
- Over-quoting in replies, or top-posting.
- Claiming "done/ready" when tests are flaky or missing — say so instead.
