---
name: commit
description: >-
  Create a git commit following PostgreSQL commit message conventions.
  Analyzes staged/unstaged changes and composes a properly formatted summary
  line, narrative body, and attribution tags (Author/Reviewed-by/Discussion).
  Use whenever the user asks to commit work in a PostgreSQL worktree — "commit
  this", "make a commit", "コミットして", "コミットメッセージを書いて". Also use whenever the
  task is to produce a patch to submit to pgsql-hackers, because a submittable
  patch (git format-patch) is built from a commit and needs a conventional
  message: "create a patch", "make a patch", "format-patch", "パッチを作成",
  "パッチ作成", "パッチにして", "パッチ作成からメール作成まで". This means a request that only
  names the downstream step (patch or mail) still triggers the commit first.
  Trigger even when the user does not say "commit" explicitly or mention
  PostgreSQL conventions.
---

# PostgreSQL Commit

Create a git commit following PostgreSQL's commit message conventions.

## Steps

1. Run `git status` to see untracked and modified files
2. Run `git diff` and `git diff --cached` to see all changes
3. Run `git log --oneline -5` to see recent commit style
4. Analyze the changes and compose a commit message following the rules below
5. Stage appropriate files (avoid secrets, .env, credentials)
6. Create the commit
7. Verify with `git log -1`

If the user provides arguments, use them as guidance for the commit message:
$ARGUMENTS

## Commit Message Format

### Summary Line (First Line)

- Write in imperative mood (e.g., "Fix", "Add", "Remove", not "Fixed", "Added", "Removed")
- Keep under 64 characters (PostgreSQL email subject limit); absolute max is around 76 characters
- Capitalize the first word (or the first word after a module prefix)
- Do not end the summary line with a period
- Use a module prefix when the change is scoped to a specific subsystem:
  `module: Summary here` (e.g., `doc:`, `psql:`, `bufmgr:`, `libpq:`,
  `jit:`, `amcheck:`, `heapam:`, `lwlock:`, `pg_dump:`, `pg_stat_statements:`)
- Common leading verbs:
  - `Fix` -- bug fixes
  - `Add` -- new features, tests, functions, or support
  - `Remove` -- deleting code, features, or dead code
  - `Use` -- switching to a different API, function, or approach
  - `Improve` -- enhancements to existing behavior, messages, or performance
  - `Update` -- updating data, comments, or dependencies
  - `Make` -- changing behavior or properties
  - `Avoid` -- preventing undesirable behavior
  - `Move` -- relocating code or files
  - `Clarify` -- making comments or docs clearer
  - `Change` -- modifying existing behavior
  - `Allow` -- enabling previously unsupported functionality
  - `Rename` -- renaming identifiers or files
  - `Refactor` -- restructuring without behavior change
  - `Simplify` -- reducing complexity
  - `Prevent` -- guarding against problematic conditions
  - `Don't` -- stopping an undesirable action
  - `Revert` -- reverting a previous commit

### Body (Narrative)

- Separate the summary from the body with a blank line
- Wrap lines at 72 characters
- Use two spaces between sentences (PostgreSQL convention)
- Explain what the change does and why it is needed
- For bug fixes: describe the problem, root cause, and how the fix addresses it
- For new features: describe what is added, why it is useful, and design decisions
- Use present tense for the current state; past tense for previous (broken) behavior
- Reference related commits by abbreviated hash (e.g., "Commit 90eae926a fixed ...")

### Tags (Attribution Section)

Tags go after the narrative body, each on its own line. The general form is:

```
Tag: <attribution> [(optional brief context)]
```

Order tags as follows:
1. Author / Co-authored-by (omit Author if the committer is the sole author)
2. Reported-by / Suggested-by / Diagnosed-by
3. Reviewed-by (separate lines for multiple reviewers)
4. Tested-by
5. Bug (the bug number, written with a leading number sign, e.g. `Bug: #18888`)
6. Backpatch-through (omit for master-only; use the oldest affected version
   like "15", a range like "13-15", or "15 only" for a single branch)
7. Discussion (use `https://postgr.es/m/MESSAGE_ID` format)

Attribution rules (from the PostgreSQL wiki guidance):

- When possible, the attribution should be a cut-and-paste of the attributed
  person's list email "From:" field, with no alterations.
- Within a single tag with multiple people, order the attributions
  approximately from "most significant participant" to "least significant".
- When committers include themselves in an attribution, they spell out their
  own attribution exactly as it appears in the "From:" field of their emails,
  just as for anyone else.
- Verbose context belongs in the narrative body; only brief context belongs in
  parentheses on a tag line.
- When the committer refers to themself in the first person in a commit
  authored or co-authored by someone else, they include a reference to their
  own name after the pronoun (e.g. "per a suggestion from me (Shinya Kato)").

### Version-specific footer

This footer applies when committing the user's own patch in a development
worktree (work destined for pgsql-hackers). The full tag set above describes
the general committer format; for the user's own patches, use this simplified
footer instead. The footer depends on whether this is the initial patch or a
later revision.

**v1 (initial patch):** use this fixed footer verbatim, leaving the
`Reviewed-by:` and `Discussion:` values blank to be filled in later:

```
Author: Shinya Kato <shinya11.kato@gmail.com>
Reviewed-by:
Discussion: https://postgr.es/m/
```

**v2 or later:**

- Keep the `Author:` line.
- If reviewers have appeared on the thread, add one `Reviewed-by:` line per
  reviewer (use each reviewer's exact "From:" field text).  If there are still
  no reviewers, leave a blank `Reviewed-by:` line.
- If the thread message ID is known, set
  `Discussion: https://postgr.es/m/MESSAGE_ID`.  Otherwise leave it as
  `Discussion: https://postgr.es/m/`.

### Anti-patterns to Avoid

- Do not use past tense in the summary line ("Fixed", "Added")
- Do not exceed the summary line length limit (aim under 64 characters, never
  more than about 76)
- Do not omit the blank line between summary and body
- Do not use "by me" in tags; spell out the full name
- Do not wrap body text beyond 72 characters
- Do not use `Co-Authored-By:` (GitHub style); use `Co-authored-by:`

## Passing the commit message via HEREDOC

Always use HEREDOC to pass multi-line commit messages:

```
git commit -m "$(cat <<'EOF'
Summary line here

Body text here.  Two spaces between sentences.

Author: Name <email>
Discussion: https://postgr.es/m/MESSAGE_ID
EOF
)"
```
