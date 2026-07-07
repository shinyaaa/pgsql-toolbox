#!/usr/bin/env bash
#
# PreToolUse(Bash) hook: deny `gh` commands that target a repository other than
# ALLOWED_REPO.  Paired with a `Bash(gh *)` allow rule so gh runs without
# prompting, while this hook blocks any cross-repo use.
#
# Target repo is determined, in order:
#   1. --repo / -R / --repo= / -R= flag value
#   2. a `repos/OWNER/NAME` path (gh api)
#   3. otherwise, inferred from the cwd's `origin` git remote
# If a repo is determined and differs from ALLOWED_REPO -> deny.  If none can be
# determined (e.g. `gh auth status`) -> allow.
set -uo pipefail

ALLOWED_REPO="shinyaaa/postgres"

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
cwd=$(printf '%s' "$input" | jq -r '.cwd // ""')

# Only guard gh commands.
printf '%s' "$cmd" | grep -Eq '(^|[;&|(){}[:space:]])gh([[:space:]]|$)' || exit 0

deny() {
	printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' \
		"$(jq -Rn --arg r "$1" '$r')"
	exit 0
}

# 1) Explicit --repo / -R flag (space or = separated).
while IFS= read -r repo; do
	[ -z "$repo" ] && continue
	[ "$repo" != "$ALLOWED_REPO" ] && \
		deny "gh command targets repo '$repo'; only $ALLOWED_REPO is allowed by the gh-repo-guard hook"
done < <(printf '%s' "$cmd" \
	| grep -oE '(--repo|-R)[=[:space:]]+[^[:space:]]+' \
	| sed -E 's/^(--repo|-R)[=[:space:]]+//')

# 2) gh api path: repos/OWNER/NAME (optional leading slash).
while IFS= read -r repo; do
	[ -z "$repo" ] && continue
	[ "$repo" != "$ALLOWED_REPO" ] && \
		deny "gh api targets repo '$repo'; only $ALLOWED_REPO is allowed by the gh-repo-guard hook"
done < <(printf '%s' "$cmd" \
	| grep -oE '/?repos/[^/[:space:]]+/[^/[:space:]]+' \
	| sed -E 's#^/?repos/##')

# 3) No explicit repo: infer from the cwd's origin remote, but skip gh
#    subcommands that are not scoped to the current repo.
sub=$(printf '%s' "$cmd" \
	| grep -oE '(^|[;&|(){}[:space:]])gh[[:space:]]+[a-zA-Z]+' \
	| head -1 | awk '{print $NF}')
case "$sub" in
	# global / not cwd-repo-scoped (api is handled above; search is cross-repo)
	auth|config|alias|extension|gist|version|completion|help|api|status|search|"")
		exit 0 ;;
esac

[ -z "$cwd" ] && exit 0
url=$(git -C "$cwd" remote get-url origin 2>/dev/null) || exit 0
repo=$(printf '%s' "$url" | sed -E 's#(\.git)?/?$##; s#^.*[:/]([^/]+/[^/]+)$#\1#')
[ -n "$repo" ] && [ "$repo" != "$ALLOWED_REPO" ] && \
	deny "gh in $cwd would target inferred repo '$repo'; only $ALLOWED_REPO is allowed by the gh-repo-guard hook"

exit 0
