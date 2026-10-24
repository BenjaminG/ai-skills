#!/usr/bin/env bash
# The babysit-prs watch: `pr-dash follow [PR…]` under <state-dir>/babysit.lock, one manager per repo.
# The lock holds this pid, which exec hands to the follower, so it is valid for the follower's life.
set -euo pipefail

command -v pr-dash >/dev/null || { echo "pr-dash not found: npm i -g github:BenjaminG/pr-dash"; exit 1; }
dir=$(pr-dash state-dir)
mkdir -p "$dir"
lock="${dir%/}/babysit.lock"

take() { (set -o noclobber; echo $$ >"$lock") 2>/dev/null; }

if ! take; then
  pid=$(cat "$lock" 2>/dev/null || true)
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "babysit-prs already active (pid $pid)"
    exit 1
  fi
  # shortcut: two watches finding the same stale lock at once can both take it; add flock if that ever happens.
  rm -f "$lock"
  take || { echo "babysit-prs already active"; exit 1; }
fi

exec pr-dash follow "$@"
