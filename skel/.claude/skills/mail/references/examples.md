# Annotated examples

Real pgsql-hackers emails, lightly annotated, as concrete models. The first
group is the user's own proposals (the voice to match). The second group shows
committer conventions worth folding in. The third shows reply/review shape.

Note: these are reproduced as they appear in the archive — i.e. hard-wrapped by
the original mailer. When *you* draft, do not hard-wrap paragraphs (the user's
client wraps them); these are here for structure and wording, not line layout.

---

## 1. The user's proposals (match this voice)

### 1a. Simple feature proposal — "Add mode column to pg_stat_progress_vacuum"

What to notice: opens with "I would like to propose a patch that …" + "The patch
is attached" up front; motivation (why the existing signals are inconvenient);
the concrete enumerated values the feature exposes; two labeled sections
("Design Considerations:", "Regarding Testing:") that pre-empt review questions —
including honestly explaining why a test was *not* added; closes with a question
and the full signature.

```
Hi hackers,

I would like to propose a patch that enhances the
pg_stat_progress_vacuum view by adding a mode column. The patch is
attached.

Although it is possible to identify an anti-wraparound VACUUM through
the process title (to prevent wraparound) or specific log entries, it
would be significantly more convenient for monitoring purposes to have
this status clearly indicated in the pg_stat_progress_vacuum view.
...
This patch introduces a mode column to provide this visibility. The
possible values are:
- normal: A standard, user-initiated VACUUM or a regular autovacuum run.
- anti-wraparound: An autovacuum run launched specifically to prevent
transaction ID wraparound.
- failsafe: A vacuum that has entered failsafe mode ...

Design Considerations:
When defining the scope of the anti-wraparound mode, I considered
including manual commands like VACUUM (FREEZE) ... However, I decided
against this to keep the meaning of the mode clear and simple. ...

Regarding Testing:
I was able to manually verify the failsafe mode's behavior by using
the existing test script at
src/test/modules/xid_wraparound/t/001_emergency_vacuum.pl. ... However,
I found this test to be somewhat flaky in my environment and decided
not to add it ...

Thought?

--
Best regards,
Shinya Kato
NTT OSS Center
```

### 1b. Feature with example + design + protocol note — "Add LIMIT option to COPY FROM"

What to notice: "I'd like to propose adding …, which …" one-liner; frames the
change as removing an *asymmetry* with existing behavior; `Syntax example:` and a
bulleted "useful for" list of real use cases; a `Design:` section covering an
edge case (protocol sync on STDIN); "The patch is attached. Thoughts?"

```
Hi hackers,

I'd like to propose adding a LIMIT option to COPY FROM, which limits
the number of rows to load.

With COPY TO, we can use the LIMIT clause in the query to restrict
output rows, but COPY FROM has no equivalent way ... This patch
resolves that asymmetry.

Syntax example:
- COPY t FROM STDIN (LIMIT 100);

This feature is useful for:
- Loading only the first N rows from a huge CSV file ...
- Sampling production data for staging or testing environments
- Preventing unexpectedly large data loads in ETL pipelines

Design:
- The LIMIT count applies after WHERE filtering and ON_ERROR skipping,
so it represents the actual number of rows inserted.
- When the source is STDIN, the server reads and discards the
remaining stream to keep the frontend/backend protocol synchronized.

The patch is attached. Thoughts?

--
Best regards,
Shinya Kato
NTT OSS Center
```

### 1c. Patch series with a focusing note — "Add wal_fpi_bytes_[un]compressed to pg_stat_wal"

What to notice: motivation framed as "Currently, we must use cumbersome methods
…" with numbered workarounds; a SQL example with the `=#` prompt and result in a
fenced block; an explicit per-patch breakdown that tells reviewers which patches
are optional and where to focus first.

```
Hi hackers,

I am proposing a patch that adds wal_fpi_bytes_[un]compressed columns
to pg_stat_wal. These columns help us calculate WAL FPI (full page
image) compression rates ...

Currently, we must use cumbersome methods to compute the WAL compression rate:
1.  Run the same benchmark twice ...
2. Run pg_waldump --fullpage and compare ...

With these patches applied, we can easily compute the FPI compression
rate with the following SQL:
=# SELECT wal_fpi_bytes_compressed / wal_fpi_bytes_uncompressed * 100
AS wal_compression_rate FROM pg_stat_wal;
  wal_compression_rate
-------------------------
 34.07161865906799706100
(1 row)

The 0001 patch adds these columns to pg_stat_wal. The 0002 and 0003
patches add this information to EXPLAIN (WAL) and pg_stat_statements,
respectively. I don't think these additions (0002 and 0003) are
mandatory, so I suggest we focus the discussion on the 0001 patch
first.

Thoughts?

--
Best regards,
Shinya Kato
NTT OSS Center
```

### 1d. RFC / spec-first (no patch yet) — "Extend COPY FROM with HEADER <integer>"

What to notice: legitimate to propose *before* writing code. States "I have not
yet created a patch, but I am willing to implement … I would like to discuss the
specification first," lays out a precise spec, cites precedent in other RDBMS
with `[N]` links.

```
Hi hackers,

I'd like to propose a new feature for the COPY FROM command to allow
skipping multiple header lines when loading data. ...

This feature also has precedent in other major RDBMS:
- MySQL: LOAD DATA ... IGNORE N LINES [1]
- SQL Server: BULK INSERT … WITH (FIRST ROW=N) [2]
- Oracle SQL*Loader: sqlldr … SKIP=N [3]

I have not yet created a patch, but I am willing to implement an
extension for the HEADER option. I would like to discuss the
specification first.

The specification I have in mind is as follows:
- Command: COPY FROM
- Formats: text and csv
- Option syntax: HEADER [ boolean | integer | MATCH] ...
- Behavior: Let N be the specified integer.
  - If N < 0, raise an error.
  - If N = 0 or 1, same behavior when boolean is specified.
  - If N > 1, skip the first N rows.

Thoughts?

[1] https://dev.mysql.com/doc/refman/8.4/en/load-data.html#...
[2] https://learn.microsoft.com/en-us/sql/t-sql/statements/bulk-insert-transact-sql#...
[3] https://docs.oracle.com/en/database/oracle/oracle-database/23/sutil/...

--
Best regards,
Shinya Kato
NTT OSS Center
```

### 1e. Aligning with an existing commit — "Enhance statistics reset functions ..."

What to notice: motivates the change by aligning with an existing commit, cited
by short hash inline: "aligns with the behavior introduced in commit dc9f8a798[1],
where pg_stat_statements_reset() was updated to return the reset time." This is
the precise-citation habit committers expect.

---

## 2. Committer conventions (fold these in)

### 2a. Un-revert / revert-aware proposal — Nathan Bossart

What to notice: opens by crediting the commits that unblocked the work
("Thanks to Jeff's recent work with commits 2af07e2 and 59825d1, …"); precisely
states the historical concern and how it was resolved; cites the developer-meeting
discussion `[0]` and the commitfest entry `[1]`; itemizes exactly how the attached
patch differs from a straight revert. Citations and precision build trust.

```
Thanks to Jeff's recent work with commits 2af07e2 and 59825d1, the issue
that led to the revert of the MAINTAIN privilege ... should now be resolved.
Specifically, there was a concern that ... Jeff's work prevents this by ...

Given this, I'd like to finally propose un-reverting MAINTAIN and
pg_maintain. I created a commitfest entry for this [1] ... The attached
patch is a straight revert of commit 151c22d except for the following
small changes:

* The catversion bump has been removed for now. ...
* The OID for the pg_maintain predefined role needed to be changed. ...
* The change in AdjustUpgrade.pm needed to be updated ...

Thoughts?

[0] https://wiki.postgresql.org/wiki/FOSDEM/PGDay_2024_Developer_Meeting#...
[1] https://commitfest.postgresql.org/47/4836/

--
Nathan Bossart
Amazon Web Services: https://aws.amazon.com
```

### 2b. Performance feature with benchmarks — Melanie Plageman

What to notice: long-form problem statement first (what aggressive vacuum costs
and why); narrative of *prior* attempts and why they fell short, each cited `[1]`;
introduces and defines new terminology; a per-patch breakdown of a 9-patch series
marking which are preliminary/WIP; **before/after benchmark output pasted as real
log blocks** plus a summary table and P99 latency; an explicit honest TODO list of
remaining benchmarking. This is the gold standard for a performance proposal.

```
Hi,

An aggressive vacuum of a relation is triggered when ... Aggressive vacuums
require examining every unfrozen tuple ... So a relation with a large number
of all-visible but not all-frozen pages may suddenly have to vacuum an order
of magnitude more pages than the previous vacuum.
...
The best solution would be to freeze the pages instead of just setting them
all-visible. But we don't want to do this if the page will be modified again ...

Last year, I worked on a vacuum patch to try and predict which pages should be
eagerly frozen [1] ...
...
v1 of this feature is attached. The first eight patches in the set are
preliminary.

I've proposed 0001-0003 in this thread [2] -- they boil down to counting pages
set all-frozen in the VM.
0004-0007 are a bit of refactoring ...
0008 is a WIP patch ...
0009 is the actual eager scanning feature.

To demonstrate the results, I ran an append-only workload ...
patch
  LOG:  automatic aggressive vacuum of table "history": index scans: 0
  vacuum duration: 44 seconds (msecs: 44661).
  ...
master
  LOG:  automatic aggressive vacuum of table "history": index scans: 0
  vacuum duration: 1201 seconds (msecs: 1201487).
  ...

   version     wal  cptr_bgwriter_w   other_rw  vac_io_time  p99_lat
    patch   770 GB          5903264  235073744   513722         1
    master  767 GB          5908523  216887764  1003654        16
...
I need to do further benchmarking and investigation to determine optimal
failure and success caps ...
I also need to try other scenarios ...

- Melanie

[1] https://www.postgresql.org/message-id/...
[2] https://www.postgresql.org/message-id/...
[3] https://www.postgresql.org/message-id/...
```

### 2c. Small, surgical fix — Peter Eisentraut

What to notice: for a tiny change, the email is correspondingly short — describe
the current hardcoded behavior, "this patch proposes to change that," explain the
mechanism, "Proposed patch attached." No ceremony. Match email length to change size.

---

## 3. Reply / review shape (bottom-posting)

Quote only what you're answering, respond below it, sign off. Example skeletons:

Revised patch, little to discuss:
```
> [trimmed quote of the comment you're addressing, if any]

Rebased the patches.

-- 
Best regards,
Shinya Kato
NTT OSS Center
```

Point-by-point review (interleaved):
```
On <date>, <Author> <addr> wrote:
> <quoted chunk 1 — the specific claim or code>

<your response to chunk 1>

> <quoted chunk 2>

<your response to chunk 2; mention the version you reviewed, e.g. "In v3, ...">

-- 
Best regards,
Shinya Kato
NTT OSS Center
```
