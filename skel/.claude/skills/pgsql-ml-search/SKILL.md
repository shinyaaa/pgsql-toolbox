---
name: pgsql-ml-search
description: >
  Search PostgreSQL mailing list archives (pgsql-hackers, pgsql-bugs, pgsql-committers, pgsql-docs)
  for past discussions, patch reviews, technical decisions, and code changes.
  TRIGGER when: user asks about PostgreSQL development history, ML/mailing list discussions,
  patch reviews, why a design decision was made, what a developer (e.g. Tom Lane, Andres Freund)
  said about a topic, or the history of a function/file change. Also trigger for Japanese queries
  like "メーリングリストを検索", "MLで議論", "パッチを探して", "hackersでの議論".
  DO NOT TRIGGER when: user asks general PostgreSQL usage questions, SQL syntax help,
  or configuration tuning unrelated to development history.
---

# PostgreSQL Mailing List Search

You have access to a PostgreSQL mailing list archive search system via MCP tools (server: `pgsql-ml-mcp`).
This archive contains messages and patches from PostgreSQL development mailing lists including
pgsql-hackers, pgsql-bugs, pgsql-committers, and pgsql-docs.

## Available MCP Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `list_mailing_lists` | List available mailing lists with message counts and date ranges | First call when unsure which lists are available or to confirm data coverage |
| `search_messages` | Search messages by keyword, identifier, or natural language | Primary search entry point — start here |
| `get_message` | Get full message body by message_id | After search, to read a specific message in detail |
| `get_thread` | Get all messages in a thread chronologically | To understand a full discussion or debate |
| `search_patches` | Search patches by file path, function name, or keyword | When looking for code changes, diffs, or patches touching specific files |
| `get_patch` | Get the raw diff of a specific patch | After search_patches, to examine the actual code change |

## Search Strategy

### Step 1: Choose the Right Search Tool

- **Looking for discussions or decisions?** → `search_messages`
- **Looking for code changes or diffs?** → `search_patches`
- **Not sure what's available?** → `list_mailing_lists` first

### Step 2: Craft the Query

`search_messages` auto-detects the query type:

**Natural language** (uses PostgreSQL full-text search with ranking):
- `vacuum freeze` — finds discussions about vacuum freeze
- `"WAL performance"` — phrase match
- `vacuum OR autovacuum` — either term
- `-autovacuum vacuum` — vacuum but not autovacuum

**Code identifiers** (uses trigram substring matching — auto-detected):
- `heapam_tuple_insert` — snake_case triggers trigram mode
- `ExecInitNode` — CamelCase triggers trigram mode
- `nbtinsert.c` — file extensions trigger trigram mode

The auto-detection works by pattern: snake_case, CamelCase, or file-extension patterns
switch to trigram search. Everything else uses full-text search. You don't need to specify
the mode — just write the query naturally.

### Step 3: Filter Results

Use optional parameters to narrow results:
- `list_name`: e.g., `"pgsql-hackers"` to search only that list
- `author`: e.g., `"Tom Lane"` for a specific developer (partial match, case-insensitive)
- `limit` / `offset`: for pagination (default 10 results, max 50)

### Step 4: Drill Down — Be Selective

Follow the hint fields in results to navigate, but be economical with tool calls:

1. `search_messages` or `search_patches` → review the returned snippets/previews first
2. Only call `get_message` for the 2-3 most relevant results, not every result
3. Only call `get_thread` when you need to understand a debate or decision process
4. Only call `get_patch` when the `diff_preview` from `search_patches` is insufficient

The goal is to answer the user's question with the minimum number of tool calls.
A single well-targeted search plus 2-3 drill-downs is usually enough.

## Efficiency Guidelines

These guidelines help you avoid wasting tokens and time on redundant work.

- **One search is often enough.** If the first `search_messages` returns relevant results,
  don't repeat with query variations. Only search again if the first query returned
  no relevant results or the user asks for more.
- **Use snippets and previews.** `search_messages` returns ranked snippets, and
  `search_patches` returns `diff_preview` (first 500 chars of the diff). Read these
  before deciding whether to fetch full content.
- **Limit deep dives.** For a summary request, read 2-3 key messages or threads.
  For a "find me X" request, the search results themselves may suffice.
- **Don't call `list_mailing_lists` unless needed.** If the user specifies a list name
  or the query is clearly about pgsql-hackers, skip it.
- **Avoid redundant `get_message` after `get_thread`.** `get_thread` already includes
  message bodies (possibly truncated). Only call `get_message` if you need the full
  untruncated body of a specific message.

## Typical Workflows

### Finding discussions about a feature or concept

```
search_messages(query="vacuum freeze", list_name="pgsql-hackers", limit=10)
→ review snippets to identify the key threads
→ get_thread(thread_id="...") for the 1-2 most important threads
→ synthesize findings for the user
```

### Finding what a developer said about a topic

```
search_messages(query="B-tree optimization", author="Tom Lane", limit=10)
→ snippets may already answer the question
→ get_message(message_id="...") only if full context is needed
```

### Finding patches that changed a specific file

```
search_patches(query="nbtinsert.c", limit=10)
→ review diff_preview and files_changed in results
→ get_patch(patch_id=...) for only the 2-3 most interesting patches
→ optionally get_message(message_id="...") for discussion context
```

### Tracing a function's history in discussions

```
search_messages(query="heapam_tuple_insert")
→ auto-detected as identifier → trigram search
→ finds all mentions including heapam_tuple_insert_speculative etc.
→ group results by thread_id to see distinct discussions
```

## Tips

- **Start broad, then narrow**: Begin with a general search and use `list_name` or `author`
  filters to focus. If too many results, add more specific terms.
- **Use thread context**: Individual messages often lack context. Use `get_thread` to understand
  the full debate, especially for contentious decisions.
- **Check for patches**: Messages with `patch_count > 0` have attached patches. Use
  `search_patches` to find and examine them.
- **Body truncation**: `get_message` truncates at 12K chars, `get_thread` manages context
  automatically. The `body_truncated` flag tells you when content was cut.
- **Combine searches**: For complex research, search messages for the discussion context
  and patches for the actual code changes separately, then synthesize.
- **Thread status**: Some threads have a `thread_status` field (e.g., "committed") indicating
  the outcome of the discussion.
