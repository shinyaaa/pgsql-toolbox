---
name: mail
description: >-
  Compose emails for the PostgreSQL pgsql-hackers mailing list in Shinya Kato's
  established writing style, following community conventions used by committers.
  Use this whenever the user wants to write, draft, or revise a pgsql-hackers
  email — a new feature/patch proposal, a reply in an existing thread (revised
  patch, addressing review feedback), or a review of someone else's patch. Also
  trigger for "/mail", "write a hackers email", "draft a proposal to -hackers",
  "メールを書いて", "提案メールを作成", "hackersに投稿", "レビュー返信", or when the user is on a
  feature branch and asks to announce/propose the work upstream.
---

# pgsql-hackers mail

Draft emails for the `pgsql-hackers@lists.postgresql.org` mailing list that read
like Shinya Kato wrote them, and that respect the community conventions
committers expect. The goal is a ready-to-send plain-text email — correct
structure, motivation-first argument, concrete examples, proper citations, and
the right signature — that the user can paste into their mail client (or
`git send-email`) with minimal editing.

## When this applies

Three email types, all on pgsql-hackers:

1. **Proposal** — the opening message of a new thread proposing a feature, patch,
   or change. This is the default when the user has a branch/patch and no thread yet.
2. **Reply** — a follow-up in an existing thread: posting a revised patch,
   answering review comments, rebasing, or discussing design.
3. **Review** — replying to someone else's patch with review feedback.

If it's ambiguous which one, ask. The branch context is a strong hint: a feature
branch with local commits and no cited thread usually means a proposal.

## Workflow

Don't dump a draft immediately. Spend a moment gathering the substance — a good
hackers email stands on its motivation and concreteness, not its prose.

1. **Identify the email type** (proposal / reply / review) and the subject matter.

2. **Gather the substance.** Pull from whatever is available before asking the user:
   - The current branch's commits and diff (`git log`, `git diff master...HEAD`) —
     the commit messages and code change usually tell you what the patch does and why.
   - For replies/reviews, the thread being responded to (ask for the message-id or
     subject; you can fetch it — see "Citations" below).
   - Ask the user only for what you genuinely can't derive: the real-world
     motivation, benchmark numbers, design alternatives they considered, which
     patches are attached, and what status the work is at (PoC / WIP / v1 / ready).

3. **Find citations** (this is expected — the user opted in). Use the pgsql-ml-search
   MCP tools to locate related prior threads, the commit that introduced a related
   feature, or a commitfest entry, and offer them as `[N]` references. See "Citations".

4. **Draft** following the structure and style below.

5. **Present** the email as: a suggested **Subject** line, then the **body** in a
   plain-text code block so the user can copy it verbatim. Note separately anything
   they still need to fill in (e.g. a benchmark number, a message-id link) and any
   attachments to add via `git format-patch`.

## Line breaks — important

Do **not** hard-wrap the body. The user's mail client inserts line breaks, so
within a paragraph write the text as a single continuous line with no manual
newlines, and let the client wrap it. Use blank lines only to separate
paragraphs, list items, and sections. (This is the one place the draft should
*not* mimic the column-wrapped look of the archived examples — those were wrapped
by the sender's mailer, not typed that way.) Keep genuine line structure where it
is semantic: separate list items, code/SQL/log blocks inside ``` fences, and the
signature lines.

## The signature

Every email ends with exactly this (the `-- ` delimiter line has a trailing space —
it's the standard sig separator):

```
-- 
Best regards,
Shinya Kato
NTT OSS Center
```

A shorter `--\nShinya Kato` appears in some quick replies, but default to the full
three-line signature.

## Style essentials (Shinya Kato's voice)

These are distilled from the user's real proposal emails. Match them closely —
they are what make a draft sound like the user rather than a generic AI.

- **Greeting:** `Hi hackers,` for a new proposal thread. (Replies: see the Reply section.)
- **Open with the proposal in the first sentence**, first person, then the payoff
  immediately. Use one of: "I am proposing a patch that …", "I would like to
  propose …", "I'd like to propose …", "I am proposing to add …". One sentence
  saying *what*, followed by *why it helps*.
- **Motivation before mechanism.** Explain the current situation and why it's
  cumbersome/insufficient before describing the solution. Use concrete pain:
  "Currently, we must use cumbersome methods to compute …", numbered lists of the
  awkward workarounds, the views one has to join, etc.
- **Be concrete.** Show, don't assert. Include SQL with the `=#` prompt, log
  output, or psql result tables inside ``` fences. Real examples are a hallmark of
  these emails.
- **Use labeled mini-sections** when the email has structure, written as a word
  followed by a colon on its own line: `Motivation:`, `Design:`,
  `Design Considerations:`, `Syntax example:`, `Example Usage:`, `Regarding Testing:`.
  Don't force them onto a short email.
- **Cite precedent in other RDBMS** when proposing user-facing syntax/behavior
  (MySQL, SQL Server, Oracle, etc.), each with a `[N]` doc link.
- **Describe the attachments plainly.** "The patch is attached." / "Two patches
  are attached." For a series, break it down per patch and say which are optional
  and where discussion should focus first: e.g. "The 0001 patch adds … The 0002
  and 0003 patches add … I don't think 0002 and 0003 are mandatory, so I suggest
  we focus on 0001 first."
- **Be honest about status.** Mark it: "This PoC patch …", "v1 …", or "I have not
  yet created a patch, but I am willing to implement … I would like to discuss the
  specification first." (RFC-style, spec-first, is a legitimate and used pattern.)
- **Close by inviting discussion** with a short question: "Thoughts?" is the
  default; "What do you think?", "Thought?", and "Do you think?" also appear.
- **References** go at the bottom as `[N] https://…` footnotes, referenced inline
  as `[N]`.
- **Tone:** plain, technical, courteous, concise. No marketing language, no
  hedging filler, no exclamation marks in the argument.
- **No semicolons.** Don't use semicolons in the prose. Split into separate
  sentences, or use a dash or "and" instead. (Quoted text from others stays
  verbatim.)

## Committer conventions to layer in

Beyond the user's own habits, fold in what committers reliably do — it raises a
proposal's credibility and is what reviewers look for. See
[references/conventions.md](references/conventions.md) for annotated examples from
committers (Nathan Bossart, Melanie Plageman, Peter Eisentraut). Highlights:

- **Lead with the problem, then why existing solutions fall short, then the
  proposal.** Reviewers decide whether to engage based on the motivation.
- **Spell out design trade-offs** — what you considered and rejected, and why. This
  pre-empts the obvious review questions.
- **Back performance claims with numbers** — before/after benchmark output, P99
  latency, WAL volume, vacuum durations. Paste real log/output blocks.
- **List open questions / TODOs explicitly** so reviewers know where input is wanted.
- **Cite prior art precisely**: related threads (message-id links), the commit that
  introduced something (short hash, e.g. `commit dc9f8a798`), and the commitfest entry.
- **Acknowledge collaborators** when the design came out of discussion with others.

## Citations

The user opted into auto-searching the archives. Use the pgsql-ml-search MCP tools
(`mcp__pgsql-ml-mcp__search_messages`, `get_message`, `get_thread`,
`search_patches`) to find:

- Related prior discussion threads → cite the root message.
- The commit/feature this builds on or aligns with → name the commit and/or its thread.
- An existing commitfest entry for this work.

Format the references the way the project does:

- Mailing-list message: `https://www.postgresql.org/message-id/<message-id>`
  (the `postgr.es/m/<message-id>` shortform is also fine).
- Commitfest entry: `https://commitfest.postgresql.org/<NN>/<NNNN>/`
- Commit: refer to it inline by short hash, e.g. "aligns with commit dc9f8a798".

Offer the citations you find and let the user confirm before baking them in — a
wrong reference is worse than none. Number them `[1]`, `[2]`, … in first-mention order.

## Replies and reviews

PostgreSQL uses **bottom-posting / interleaved quoting**, not top-posting — the
user has explicitly advocated this on-list, so honor it:

- Quote the relevant portion of the message you're answering, then write your
  response *below* that quote. For point-by-point review, interleave: quote a
  chunk, respond, quote the next chunk, respond.
- Open the quoted block with an attribution line like
  `On Fri, Oct 31, 2025 at 3:31 PM Foo Bar <foo@example.com> wrote:` followed by
  `>`-prefixed quoted lines. Trim quoted text to just what you're responding to —
  don't quote the whole message.
- For a revised patch with little to discuss, a short note suffices:
  "Rebased the patches." / "A new patch is attached. Thoughts?" — still bottom-posted,
  still signed.
- Reviews: be specific and kind. Quote the exact code/line in question, state the
  issue and the suggested fix, and separate blocking concerns from nits. Reference
  the patch version you reviewed (e.g. "In v3, …").

See [references/conventions.md](references/conventions.md) for a worked reply/review
skeleton.

## Worked proposal skeleton

Each paragraph below is one continuous line in the actual draft (no hard wrapping);
it's shown here only as the shape to fill in.

```
Hi hackers,

I am proposing a patch that <does X>, which <delivers benefit Y>.

<Motivation: the current situation and why it's cumbersome/insufficient. Concrete pain, numbered workarounds, the views/tools one must use today.>

<The proposal: what the patch does. Possible values / syntax / behavior. Use a labeled section like "Design:" if it helps.>

<A concrete example in a fenced block — SQL with =# prompt, log output, or a result table.>

<For user-facing syntax, precedent in other RDBMS with [N] links.>

<Attachments: "The patch is attached." or a per-patch breakdown for a series, noting optional patches and where to focus discussion first.>

Thoughts?

[1] https://...
[2] https://...

-- 
Best regards,
Shinya Kato
NTT OSS Center
```

Detailed annotated real examples — the user's own and committers' — are in
[references/examples.md](references/examples.md). Read it when you want a concrete
model to follow for a specific email type.
