#!/usr/bin/env bash
# bump-version.sh — bump the plugin version across all manifests and tag a release.
#
# Keeps .claude-plugin/plugin.json, .codex-plugin/plugin.json, and
# .antigravity-plugin/plugin.json in lockstep, then
# (unless -n) commits the change and creates an annotated git tag vX.Y.Z. Does NOT
# push — review the commit/tag, then `git push && git push --tags` yourself.
#
# The Claude plugin's version field is what `/plugin update` compares: users only
# get an update when this number changes. Bump it on every release you want to ship.
#
# Usage:
#   scripts/bump-version.sh <major|minor|patch|X.Y.Z> [-n] [-m <msg>]
#
# Options:
#   <bump>   major | minor | patch, or an explicit semver like 1.4.0. REQUIRED.
#   -n       No commit/tag — only rewrite the manifests (dry-ish, leaves them staged-free).
#   -m       Commit/tag message override. Default: "release vX.Y.Z".
#   -h       Show this help.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_MANIFEST="$ROOT/.claude-plugin/plugin.json"
CODEX_MANIFEST="$ROOT/.codex-plugin/plugin.json"
ANTIGRAVITY_MANIFEST="$ROOT/.antigravity-plugin/plugin.json"
MANIFESTS=("$CLAUDE_MANIFEST" "$CODEX_MANIFEST" "$ANTIGRAVITY_MANIFEST")

usage() { sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; }

BUMP="" NOCOMMIT=0 MSG=""
while [ $# -gt 0 ]; do
  case "$1" in
    -n) NOCOMMIT=1; shift ;;
    -m) MSG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) BUMP="$1"; shift ;;
  esac
done

[ -n "$BUMP" ] || { echo "error: pass major|minor|patch or an explicit X.Y.Z" >&2; usage >&2; exit 1; }
command -v jq >/dev/null || { echo "error: jq is required" >&2; exit 1; }
for f in "${MANIFESTS[@]}"; do
  [ -f "$f" ] || { echo "error: missing $f" >&2; exit 1; }
done

CUR="$(jq -r '.version // "0.0.0"' "$CLAUDE_MANIFEST")"
[[ "$CUR" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "error: current version '$CUR' is not semver" >&2; exit 1; }
IFS='.' read -r MAJ MIN PAT <<<"$CUR"

case "$BUMP" in
  major) NEW="$((MAJ+1)).0.0" ;;
  minor) NEW="${MAJ}.$((MIN+1)).0" ;;
  patch) NEW="${MAJ}.${MIN}.$((PAT+1))" ;;
  [0-9]*.[0-9]*.[0-9]*)
    [[ "$BUMP" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "error: '$BUMP' is not valid semver" >&2; exit 1; }
    NEW="$BUMP" ;;
  *) echo "error: '$BUMP' must be major|minor|patch or X.Y.Z" >&2; exit 1 ;;
esac

[ "$NEW" != "$CUR" ] || { echo "error: new version equals current ($CUR) — nothing to bump" >&2; exit 1; }
echo ">> $CUR -> $NEW"

# Rewrite all manifests, preserving key order (version stays where it already sits;
# for a manifest lacking it, jq appends it — order is cosmetic, not semantic).
for f in "${MANIFESTS[@]}"; do
  tmp="$(mktemp)"
  jq --arg v "$NEW" '.version = $v' "$f" > "$tmp"
  mv "$tmp" "$f"
  echo "   updated $f"
done

if [ "$NOCOMMIT" -eq 1 ]; then
  echo ">> -n set: manifests rewritten, no commit/tag. Review with: git diff"
  exit 0
fi

[ -z "$(git -C "$ROOT" status --porcelain "${MANIFESTS[@]}")" ] \
  && { echo "error: manifests unchanged in git — aborting commit" >&2; exit 1; }

MSG="${MSG:-release v$NEW}"
git -C "$ROOT" add "${MANIFESTS[@]}"
git -C "$ROOT" commit -m "chore(release): v$NEW"
git -C "$ROOT" tag -a "v$NEW" -m "$MSG"

cat <<EOF

>> committed and tagged v$NEW (not pushed).
   push with:  git push && git push origin v$NEW
EOF
