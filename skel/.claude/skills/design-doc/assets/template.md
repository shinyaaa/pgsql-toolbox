# Design Doc: <feature name>

<!-- Guidance comments like this one are for the writer; delete them from the
finished doc. Structure and principles: see SKILL.md and references/exemplars.md. -->

- **Status**: Draft | Proposed | Under discussion | Committed | Withdrawn
- **Date**: YYYY-MM-DD
- **Branch**: <worktree branch>
- **Thread**: <-hackers thread URL, filled in after posting>

## 1. Problem

<!-- Two paragraphs max. Who is hurt and how, before any mechanism. Current
behavior and its real cost to users/operators, with measurements where
possible (Andres: "1 million empty tables → any stats access takes ~0.4s,
170MB"). Why now, and why in core (Haas: several companies each maintain an
out-of-core solution). -->

## 2. Prior art

<!-- Earlier threads, sunk patches, out-of-core tools — found via
pgsql-ml-search, cited as [N]. For each: one line on what it did, one line on
how this design differs. Be respectful of sunk efforts; their authors may
review this. -->

## 3. Goals / Non-goals

### Goals

<!-- What v1 achieves. Three to five bullets. -->

### Non-goals (future work)

<!-- What this deliberately does not do. Park adjacent work explicitly
("that sounds like a separate effort") and nice-to-haves ("not a must-have
for v1"). Undeclared scope is what threads drown in. -->

## 4. Proposal overview

<!-- One or two paragraphs. Reading only this section should convey the whole
design. Lead with the user-visible change (new GUC, tool, syntax) — focus on
the user experience, not the technology. -->

## 5. Design

<!-- Numbered components (Haas: block selection / file format / merge tool),
half a page each at most. Per component: mechanism, alternatives considered
and why rejected, and a concrete usage scenario where it helps (Haas's
day1/day2/day9 rotation). It is fine to leave non-essential choices open with
the trade-offs listed — decide only what must be decided. -->

### 5.1 <component>

### 5.2 <component>

## 6. Evidence / benchmarks

<!-- Numbers with their conditions: workload, environment, master commit
compared against. Honest qualifiers ("contrived", "as much as") are
load-bearing. No code yet? Replace with: "This is just a design proposal at
this point; there is no code." No measurements yet? Say so and name the
planned workload. -->

## 7. Known weaknesses

<!-- Cases where this design performs badly or is incomplete, listed before a
reviewer finds them (Munro: "Here are some cases where I expect this patch to
perform badly:"). Each with a mitigation sketch where you have one, and an
honest "I haven't looked into this" where you don't. -->

## 8. Open questions

<!-- Each question carries your leaning ("My gut feeling here is...").
A bare question delegates your homework to the list. A question big enough
for its own thread graduates to an ADR (assets/adr-template.md). -->

## 9. References

<!-- [1] https://www.postgresql.org/message-id/...  — matched to inline [N]. -->
