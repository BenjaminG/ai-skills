#!/usr/bin/env bash
# PostToolUse hook for the ai-skills repo.
# After a successful `git push` that actually transfers commits, runs
# `npx skills update` for every skill directory under skills/ that those
# commits touched.
#
# Triggers only when:
#   - Bash command starts with `git push`
#   - cwd is this repo
#   - exit code is 0
#   - git push output contains an `old..new` range (i.e. commits moved,
#     not "Everything up-to-date")

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

input="$(cat)"

cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
command=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
exit_code=$(printf '%s' "$input" | jq -r '.tool_response.exit_code // .tool_response.exitCode // 0')
# git push writes the ref-update line to stderr; Claude Code captures both
# streams in tool_response output fields. Probe the common ones.
output=$(printf '%s' "$input" | jq -r '
  [
    .tool_response.stderr // "",
    .tool_response.stdout // "",
    .tool_response.output // "",
    .tool_response.interrupted // "",
    .tool_response.error // ""
  ] | join("\n")')

[[ -z "$command" ]] && exit 0
[[ "$cwd" != "$REPO_ROOT" ]] && exit 0
[[ "$exit_code" != "0" ]] && exit 0

if ! [[ "$command" =~ (^|[[:space:]\;\&\|])git[[:space:]]+push([[:space:]]|$) ]]; then
  exit 0
fi
[[ "$command" == *"--dry-run"* ]] && exit 0

# Extract `<old>..<new>` from git push output, e.g.
#   "   abc1234..def5678  main -> main"
# A forced push prints `+ old...new`; a new branch prints `* [new branch]`.
# We only handle the fast-forward / forced cases (existing branch update).
range=$(printf '%s' "$output" \
  | grep -Eo '[0-9a-f]{7,40}\.\.\.?[0-9a-f]{7,40}' \
  | head -n1 || true)

[[ -z "$range" ]] && exit 0

# Normalize `a...b` (forced) to `a..b` for git diff.
range=${range//.../..}

cd "$REPO_ROOT"

old_sha=${range%%..*}
new_sha=${range##*..}

# Verify both refs exist locally; if not, bail rather than guess.
git cat-file -e "$old_sha" 2>/dev/null || exit 0
git cat-file -e "$new_sha" 2>/dev/null || exit 0

changed_skills=$(git diff --name-only "$old_sha" "$new_sha" \
  | awk -F/ '$1 == "skills" && NF>2 {print $2}' \
  | sort -u \
  | while read -r dir; do
      [[ -f "$REPO_ROOT/skills/$dir/SKILL.md" ]] && echo "$dir"
    done)

[[ -z "$changed_skills" ]] && exit 0

# shellcheck disable=SC2086
skills_args=$(printf '%s ' $changed_skills)

log="$REPO_ROOT/.claude/hooks/skills-update.log"
{
  echo "=== $(date -Iseconds) push: $range ==="
  echo "skills: $skills_args"
  # shellcheck disable=SC2086
  npx -y skills update -g -y $skills_args 2>&1 || echo "(update failed)"
} >>"$log" 2>&1 &

cat <<JSON
{"systemMessage": "skills update queued for: ${skills_args% }"}
JSON
