# Exemplar proposals — annotated breakdowns

Four pgsql-hackers messages whose structure this skill is extracted from.
Each entry: link, what kind of doc it models, its skeleton, and the moves
worth copying. Quotes are verbatim.

## 1. Robert Haas — "block-level incremental backup" (2019-04-09)

https://www.postgresql.org/message-id/CA+TgmoYxQLL=mVyN90HZgH0X_EUrw+aZ0xsXJk7XV3-3LygTvA@mail.gmail.com

**Models: the design-first proposal (no code yet).** The purest design doc of
the four — "This is just a design proposal at this point; there is no code."

Skeleton:
1. Problem as an ecosystem observation: "Several companies, including
   EnterpriseDB, NTT, and Postgres Pro, have developed technology that
   permits a block-level incremental backup" — each maintaining its own
   out-of-core solution, so it belongs in core.
2. Design as three numbered components: (1) server-side block selection,
   (2) partial-file format, (3) a new merge tool (`pg_combinebackup`).
3. "Other random points" — a grab-bag of alternatives, risks, and scope cuts.

Moves worth copying:
- **Deliberately underspecifies non-essential choices.** For block selection
  he lists three strategies (full scan, WAL scan, modified-block map) and
  says "I am at the moment not too concerned with the exact strategy we use
  here... we may want to eventually support more than one, since they have
  different trade-offs." Decide what must be decided, keep the rest open —
  it invites collaboration instead of bikeshedding.
- **Concrete operational scenario**: the day1/day2/day9 rotation example
  ("pg_combinebackup day1 day2 -o full; rm -rf day1 day2...") shows the user
  experience before any implementation detail.
- **Explicit scope cuts as "separate efforts"**: parallel backup, object
  store targets — acknowledged, then parked. "This doesn't seem like a
  must-have for v1, though."
- **Respect for sunk prior attempts**: "I know that there have been several
  previous efforts in this area... I intend no disrespect to those efforts.
  I believe I'm taking a slightly different view of the problem here...
  trying to focus on the user experience rather than, e.g., the technology."
- Ends with a single word of invitation: "Thoughts?"

## 2. Thomas Munro — "WIP: WAL prefetch (another approach)" (2020-01-01)

https://www.postgresql.org/message-id/CA+hUKGJ4VJN8ttxScUFM8dOKX0BrBiboo5uz1cq=AovOddfHpA@mail.gmail.com

**Models: the WIP-patch proposal with benchmarks.** Closest to the user's
usual situation (working branch + measurements in hand).

Skeleton:
1. Idea in one paragraph, anchored to earlier discussions "[1][2]" from the
   first sentence.
2. Result with conditions attached: "in contrived larger-than-memory pgbench
   crash recovery experiments... as much as 20x faster with
   full_page_writes=off". Note "contrived" and "as much as" — the honesty is
   load-bearing.
3. "Some notes:" — platform constraints, PoC shortcuts, known-incomplete
   parts (timeline changes unhandled).
4. "Earlier work, and how this patch compares:" — one paragraph per prior
   effort (pg_prefaulter, Knizhnik's process), each ending in a precise
   differentiation.
5. **"Here are some cases where I expect this patch to perform badly:"** —
   four failure modes, each with a sketched mitigation and, where true, "I
   haven't looked into this."

Moves worth copying:
- The self-declared weakness section is the single most distinctive move in
  the corpus. It converts every predictable attack into a pre-listed
  discussion item.
- Weakness entries pair a mechanism ("all the WILLNEED advice prevents
  Linux's automagic readahead from working well") with a mitigation sketch
  ("perhaps... detect up to N concurrent streams") — showing the failure is
  understood, not just noticed.
- Footnote references include a conference talk and a GitHub repo of
  experiments, not just threads — evidence can live anywhere, cite it.

## 3. Andres Freund — "shared memory stats: high level design decisions:
consistency, dropping" (2021-03-19)

https://www.postgresql.org/message-id/20210319235115.y3wz7hpnnrshdyv6@alap3.anarazel.de

**Models: the ADR.** Not a feature proposal — a thread created solely to
settle two decisions.

Skeleton:
1. Why a separate thread: the implementation thread "is quite long and most
   are probably skipping over new messages in it"; these two decisions
   "warrant a wider audience". Low-level discussion explicitly stays in the
   other thread.
2. Minimal context for outsiders: "In case it is not obvious, the goal of
   the shared memory stats patch is..." — two paragraphs, no more.
3. Decision 1 with sub-questions 1.1 / 1.2 / 1.3, each independently
   answerable. Decision 2 as its own numbered section.
4. Status quo costs measured: "with a database that contains 1 million empty
   tables, any stats access takes ~0.4s and increases memory usage by 170MB."
5. His own position on every question: "I personally think it's fine to have
   short-term divergences between the columns."
6. A gut-feeling recommendation including a staged path: "My gut feeling
   here is to try to fix the remaining issues in the 'collect oids' approach
   for 14 and to try to change the approach in 15. And, if that proves too
   hard... But I'm also not sure - it might be smarter to go full in, to
   avoid introducing a system that we'll just rip out again."
7. Ends: "Comments?"

Moves worth copying:
- **Decomposition into independently answerable sub-questions** is what makes
  the thread convergent — reviewers can agree with 1.1 while debating 1.3.
- Rejects an alternative with a *user-visible confusion scenario*, not
  abstract argument: the one-entry cache would mean "Access stats for the
  same relation multiple times in a row? Do not see updates. Switch between
  e.g. a table and its indexes? See updates."
- Names design smells frankly: keeping the old model's snapshot behavior
  would be "cargo-culting an efficiency hack required by the old storage
  model forward."
- Stating uncertainty ("But I'm also not sure") does not weaken the doc —
  it marks exactly where input is wanted.

## 4. Robert Haas — "backup manifests" (2019-09-18)

https://www.postgresql.org/message-id/CA+TgmoZV8dw1H2bzZ9xkKwdrk8+XYa+DC9H=F7heO2zna5T6qg@mail.gmail.com

**Models: the follow-up design doc after a design broke.** Spun out of the
incremental-backup thread when testing falsified the original design.

Skeleton:
1. Dense provenance: eight footnotes in the first paragraph reconstruct who
   suggested what and where.
2. Public correction without defensiveness: "some of my colleagues figured
   out that my design was broken, because my proposal was to detect new
   blocks just using LSN, and that ignores the fact that CREATE DATABASE and
   ALTER TABLE .. SET TABLESPACE do physical copies without bumping page
   LSNs, which I knew but somehow forgot about." Then what follows from the
   correction.
3. Requirements derived with rationale, including future-proofing:
   checksum algorithms "that used to seem like good choices (e.g. MD5) no
   longer do; this trend can probably be expected to continue" — so the
   format must allow algorithm choice. Pre-empts bikeshedding by offering
   SHA-224/256/384/512 all at once.
4. Capabilities as a numbered list of three verbs (generate / reconstruct /
   verify a manifest).
5. Open question with a leaning: "One thing I'm not quite sure about is
   where to store the backup manifest... I suppose then we should just write
   the manifest into the top level of the main data directory, but perhaps
   someone has another idea." Ends: "Ideas?"

Moves worth copying:
- When a design changes, **document the falsification, not just the new
  design** — the "why not the obvious simpler thing" record is what saves
  the next person (or the next thread) from relitigating it.
- Design for the successor of your current choice (checksum agility) and say
  why.
- Heavy, precise citation is a feature: every claim about who said what
  links to the message. Do the same via pgsql-ml-search.

## Cross-cutting summary

All four share, in some order: problem stated as who is hurt → prior art
with explicit differentiation → design in numbered components → costs and
evidence with conditions attached → self-declared weaknesses or falsified
assumptions → explicit v1 scope cut → open questions each carrying the
author's leaning → a one-word invitation to the list. The design doc
template mirrors exactly this sequence.
