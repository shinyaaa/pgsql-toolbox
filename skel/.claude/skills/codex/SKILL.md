---
name: codex
description: >-
  Call OpenAI Codex CLI for a second opinion when stuck or for code review.
  Usage - /codex review, /codex ask <question>, /codex <prompt>. Also use when
  the user asks for "another model's opinion", "a second opinion",
  "Codexに聞いて", "セカンドオピニオン", or wants an independent review of
  uncommitted changes.
---

# Codex Second Opinion

Call the OpenAI Codex CLI to get a second opinion or code review.

## Arguments

$ARGUMENTS

## Preflight

Check that the CLI exists (`command -v codex`). If it is not installed, tell
the user and stop — do not try to install it yourself (it needs an OpenAI
account; typically installed via `npm install -g @openai/codex`).

## Mode Selection

Select mode based on arguments:

- Starts with `review` → **Review mode**
- Starts with `ask` → **Ask mode** (pass the rest as a prompt)
- Other text → **Exec mode** (pass text as-is as a prompt)
- No arguments → **Review mode** (default)

## Review Mode

Run a code review on uncommitted changes.

1. Run `git diff --stat` to confirm what will be reviewed
2. Execute:

```
codex review --uncommitted
```

If there is extra text after `review` (e.g., `/codex review focus on security`), pass it as custom instructions:

```
codex review --uncommitted "<extra instructions>"
```

3. Summarize the Codex output, listing key findings

## Ask Mode

Ask Codex a question in the context of the current working directory.

1. Execute:

```
codex exec -s read-only "<question>"
```

2. Present the Codex answer. If it conflicts with your own analysis, show both perspectives and let the user decide.

## Exec Mode

Run Codex non-interactively with an arbitrary prompt.

1. Execute:

```
codex exec -s read-only "<prompt>"
```

2. Present the Codex output.

## Common Rules

- If Codex output is long, summarize key points
- If Codex's suggestion conflicts with your analysis, present both views and let the user decide
- Always use `read-only` sandbox or `--uncommitted` to prevent Codex from making write operations
- Use a 120-second timeout for Codex commands. Reviews of large diffs can take
  longer — if a command times out, re-run it in the background and report the
  result when it completes instead of giving up
- Codex output is a second opinion, not ground truth — verify concrete claims
  (line numbers, API behavior) against the actual code before relaying them
