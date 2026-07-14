# ADR: <decision title>

<!-- One decision per ADR. Model: Andres Freund "shared memory stats: high
level design decisions" — see references/exemplars.md §3. Guidance comments
are for the writer; delete them from the finished doc. -->

- **Status**: Open | Decided | Superseded by <ADR>
- **Date**: YYYY-MM-DD
- **Related**: <design doc / implementation thread URL / commit>
- **Decision owner**: <you, or awaiting committer judgment>

## Context

<!-- Why this decision needs settling now, and why in its own doc/thread
(Andres: the implementation thread is long, these questions "warrant a wider
audience"). Two or three paragraphs of background for readers who don't know
the patch ("In case it is not obvious, the goal of ... is to ..."). What
happens if it stays unsettled (rework, missed release). -->

## Question(s)

<!-- The decision, phrased as questions. Decompose into independently
answerable sub-questions (1.1, 1.2, ...) — that is what lets reviewers agree
with 1.1 while debating 1.3, and makes the thread convergent. -->

## Status quo

<!-- Current behavior, its historical rationale, and its measured cost.
"Keep the status quo" is always one of the options, so present it fairly —
but name it when a behavior only exists to serve the old design ("cargo-
culting an efficiency hack required by the old storage model forward"). -->

## Options

<!-- Per option: summary, implementation cost, consequences (user-visible
behavior, performance, maintainability). If a collaborator already tried an
option, include it respectfully and reject it with a concrete user-visible
scenario, not abstract argument (Andres on the one-entry cache: "Access
stats for the same relation multiple times in a row? Do not see updates.
Switch between e.g. a table and its indexes? See updates."). -->

### Option A: <name>

### Option B: <name>

## My take

<!-- Your position on every question, with its confidence level stated
honestly — "gut feeling" is acceptable and useful. Staged paths are options
too (safe A this release, B next). Recorded hesitation is information:
"But I'm also not sure - it might be smarter to go full in, to avoid
introducing a system that we'll just rip out again." -->

## Decision

<!-- Filled when settled: what was decided, when, the deciding argument, and
the message URL. Until then leave empty with Status: Open. -->

## References

<!-- [1] https://www.postgresql.org/message-id/... -->
