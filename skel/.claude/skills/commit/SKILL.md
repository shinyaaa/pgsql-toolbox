---
name: commit
description: Create a git commit following PostgreSQL commit message conventions. Analyzes staged/unstaged changes and composes a properly formatted commit message.
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

Tags go after the narrative body, each on its own line:

```
Tag: Full Name <email@example.com>
```

Order tags as follows:
1. Author / Co-authored-by (omit Author if the committer is the sole author)
2. Reported-by / Suggested-by / Diagnosed-by
3. Reviewed-by (separate lines for multiple reviewers)
4. Tested-by
5. Bug
6. Backpatch-through (omit for master-only; use version like "15" or range like "13-15")
7. Discussion (use `https://postgr.es/m/MESSAGE_ID` format)

### Anti-patterns to Avoid

- Do not use past tense in the summary line ("Fixed", "Added")
- Do not exceed 72 characters in the summary line
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
