---
name: design-doc
description: >-
  Write a design doc (or an ADR for a single contested decision) for a
  PostgreSQL feature before proposing it on pgsql-hackers, structured the way
  respected committers structure their proposals (Robert Haas, Thomas Munro,
  Andres Freund). Use this whenever the user wants to organize the design of a
  feature branch before mailing, asks for a design doc, ADR, or design record,
  or says "設計ドキュメント", "デザインドック", "design docを書いて", "ADRを書いて",
  "提案の前に設計をまとめたい", "設計判断を整理したい". Also trigger when the user is
  about to propose a large feature and the motivation, trade-offs, or scope are
  not yet written down anywhere — the design doc comes before the /mail draft.
---

# PostgreSQL design doc

Produce a design doc for a feature the user intends to propose on
pgsql-hackers, or an ADR for one contested design decision. The doc is the
durable, complete record of the design: problem, prior art, alternatives,
evidence, weaknesses, and open questions. The proposal email (the `mail`
skill) is a *trimmed projection* of this doc, so completeness lives here and
brevity lives there. A good design doc also outlives the thread — it is what
the user rereads months later when the discussion resumes or the proposal is
resubmitted.

The structure is not invented. It is extracted from how committers whose
proposals succeed actually write them: Robert Haas's "block-level incremental
backup" and "backup manifests", Thomas Munro's "WAL prefetch (another
approach)", and Andres Freund's "shared memory stats: high level design
decisions". Read [references/exemplars.md](references/exemplars.md) for the
annotated breakdowns before writing your first doc in a session — the
principles below are compressed from it.

## Design doc or ADR?

- **Design doc** — one feature, the whole design. Default for a feature branch
  heading toward a proposal. Template: [assets/template.md](assets/template.md).
- **ADR** — one decision with real trade-offs that needs community (or future-
  self) buy-in. Use it when a single open question in a design doc grows big
  enough to deserve its own thread, the way Andres split two decisions out of
  the shared-memory-stats thread "to warrant a wider audience". Template:
  [assets/adr-template.md](assets/adr-template.md).

One decision = one ADR. If the user brings a pile of questions, split them.

## Workflow

1. **Gather the substance before writing.** Pull from what exists first:
   `git log master..HEAD`, `git diff master...HEAD --stat`, commit messages,
   benchmark results in `work/<branch>/`, and any earlier /mail drafts
   (`work/<branch>/vN.md`). Ask the user only for what you cannot derive:
   real-world motivation, numbers not yet measured, alternatives they already
   rejected and why, and the intended v1 scope.

2. **Search prior art — always.** Use the pgsql-ml-search MCP tools
   (`mcp__pgsql-ml-mcp__search_messages`, `get_thread`, `search_patches`) to
   find earlier threads, sunk patches, and out-of-core tools in the same
   space. Prior art is the credibility backbone of the doc: every exemplar
   proposal cites what came before and states precisely how it differs. A
   proposal that reinvents a known sunk patch gets that pointed out in the
   first reply, so find it now. Record findings in the Prior art section with
   message-id links, and note for each one how this design differs.

3. **Fill the template.** Copy the section skeleton from
   [assets/template.md](assets/template.md) (or the ADR one) and write the
   body in English — sections get lifted into the English proposal mail, so
   drafting in Japanese just adds a translation pass. Keep the template's
   guidance comments out of the final doc. Apply the writing principles below
   as you go, and don't force empty sections: a doc with no benchmarks yet
   says so in one line ("No measurements yet; planned workload: ...") rather
   than padding.

4. **Save it.** Write to `work/<branch>/design-doc.md` (ADR:
   `work/<branch>/adr-<slug>.md`). If the doc revises substantially after
   feedback, keep it as one file and update in place — unlike patches, the
   design doc is a living document, and git in `~/git/pgsql-toolbox` provides
   history if archived. When the proposal is posted, offer to archive a copy
   to `~/git/pgsql-toolbox/docs/designs/<branch>.md` with the thread URL
   filled in, since the user keeps finished design records in that repo.

5. **Hand off.** Tell the user the path, list what still needs their input
   (unmeasured numbers, undecided scope), and note that `/mail` can generate
   the proposal email from the doc when they are ready.

## Writing principles

These six are what the exemplars have in common. They are the difference
between a doc that survives contact with reviewers and one that does not.

1. **Start from who is hurt, not from the mechanism.** Haas opened with
   "several companies have each built their own out-of-core incremental
   backup" — a problem statement about the ecosystem, before any design. If
   the problem section reads like a feature description, rewrite it.

2. **Cite prior art and say how you differ.** Munro named pg_prefaulter and
   Knizhnik's patch and gave each a paragraph of "mine differs in that...".
   Respect sunk efforts explicitly (Haas: "I intend no disrespect to those
   efforts") — some of their authors will be your reviewers.

3. **List your weaknesses before reviewers do.** Munro's "here are some cases
   where I expect this patch to perform badly" is the model: each weakness
   with a possible mitigation and an honest "I haven't looked into this"
   where true. A weakness you name is a discussion item; one a reviewer finds
   is a credibility hit.

4. **Cut v1 scope in writing.** Name the things you are deliberately not
   doing and park them as future work ("that sounds like a separate effort",
   "not a must-have for v1"). Undeclared scope is what threads drown in.

5. **Numbers carry their conditions.** Munro reported "as much as 20x faster"
   only alongside "contrived larger-than-memory pgbench" and
   "full_page_writes=off". A number without workload, environment, and the
   master commit it was measured against will be challenged, and rightly so.

6. **Every open question carries your leaning.** Andres: "My gut feeling here
   is to fix X for 14 and change the approach in 15." A bare question
   delegates your homework to the list; a question with a leaning invites a
   decision. Uncertainty is fine to state, unowned questions are not.

## Write it lean

"Complete" means every section is covered, not that every section is long.
The doc's value is how fast it re-loads into a reader's head months later,
and the exemplars themselves are dense, not lengthy — Andres settled two
major decisions in under two screens. Default budgets: Problem and Proposal
overview two paragraphs each, one short paragraph per prior-art entry, half
a page per design component, one line per goal and non-goal. Use bullets for
anything enumerable. State each fact in exactly one section and let others
refer to it instead of restating it. The mail skill's deletion patterns
apply here too: no translation tails re-explaining the previous sentence, no
prose repeating what a table or code block already shows, no closing
summary. A section with nothing to say yet gets one line saying so, not a
padded paragraph. After drafting, do a trim pass — if it removed nothing, it
wasn't a real pass.

## Relationship to the mail skill

The design doc is upstream of the proposal email, and they deliberately pull
in opposite directions: the doc is complete, the mail is short. When the user
runs `/mail` afterward, the mapping is roughly:

| Design doc section | In the proposal mail |
|---|---|
| Problem | Opening motivation, compressed to a few sentences |
| Prior art | `[N]` citations |
| Proposal overview + Design | The body, with only the load-bearing components |
| Evidence | One pasted benchmark block |
| Known weaknesses | One or two honestly named, rest held for replies |
| Non-goals | A one-line scope statement |
| Open questions | The closing questions to the list |

Do not let the doc's completeness leak into the mail — the mail skill's "keep
it short" rule wins there. The doc is where the full argument lives so the
mail can afford to be brief.
