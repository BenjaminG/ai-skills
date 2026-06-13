#!/usr/bin/env bash
# select-corpus.sh — build a style-extraction corpus for a single author.
#
# Computes per-file line ownership via git blame (after a cheap author
# pre-filter so it stays tractable on large repos) and keeps only files the
# author dominates. No external dependencies beyond git/awk/coreutils.
#
# Usage:
#   select-corpus.sh -a <author-pattern> [opts]
#
# Options:
#   -a  Author pattern (substring, matches name OR email in git blame). REQUIRED.
#   -s  Path scope (pathspec), default: "."
#   -d  Window passed to --since, default: "6 months ago"
#   -t  Ownership threshold % to keep a file, default: 50
#   -n  Max files to keep, default: 40
#   -o  Output dir, default: "./.mimic-corpus"
#   -g  Comma-separated extensions, default: "ts,tsx,js,jsx"
#   -h  Show this help.
set -euo pipefail

AUTHOR="" SCOPE="." SINCE="6 months ago" THRESHOLD=50 MAXFILES=40
OUTDIR="./.mimic-corpus" EXTS="ts,tsx,js,jsx"

while getopts "a:s:d:t:n:o:g:h" opt; do
  case "$opt" in
    a) AUTHOR="$OPTARG" ;;
    s) SCOPE="$OPTARG" ;;
    d) SINCE="$OPTARG" ;;
    t) THRESHOLD="$OPTARG" ;;
    n) MAXFILES="$OPTARG" ;;
    o) OUTDIR="$OPTARG" ;;
    g) EXTS="$OPTARG" ;;
    h) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "see -h" >&2; exit 2 ;;
  esac
done

[ -n "$AUTHOR" ] || { echo "error: -a <author-pattern> is required" >&2; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "error: not inside a git work tree" >&2; exit 1; }

mkdir -p "$OUTDIR"
EXT_RE="\.($(echo "$EXTS" | tr ',' '|'))$"

echo ">> author='$AUTHOR' scope='$SCOPE' since='$SINCE' threshold=${THRESHOLD}% max=$MAXFILES" >&2

# 1. Commit log (granularity / message style signal)
git log --author="$AUTHOR" --no-merges --since="$SINCE" \
  --pretty=format:'%h|%ad|%s' --date=short -- "$SCOPE" \
  > "$OUTDIR/commits.txt" 2>/dev/null || true

COMMITS=$(grep -c . "$OUTDIR/commits.txt" || true)

# 2. Cheap pre-filter: files the author touched in scope+window, by extension
git log --author="$AUTHOR" --no-merges --since="$SINCE" \
  --name-only --pretty=format: -- "$SCOPE" 2>/dev/null \
  | grep -E "$EXT_RE" | sort -u > "$OUTDIR/.candidates.txt" || true
CAND=$(grep -c . "$OUTDIR/.candidates.txt" || true)
echo ">> $COMMITS commits, $CAND candidate files — computing line ownership..." >&2

# 3. Per-file ownership via blame on the current tree
: > "$OUTDIR/ownership.tsv"
while IFS= read -r f; do
  [ -f "$f" ] || continue
  git blame --line-porcelain -- "$f" 2>/dev/null | awk -v pat="$AUTHOR" -v file="$f" '
    /^author / || /^author-mail / { if (index($0, pat) > 0) hit=1 }
    /^\t/ { total++; if (hit) mine++; hit=0 }
    END {
      if (total > 0) printf "%d\t%d\t%d\t%s\n", int(mine*100/total), mine, total, file
    }' >> "$OUTDIR/ownership.tsv"
done < "$OUTDIR/.candidates.txt"

sort -t$'\t' -k1,1nr -k3,3nr "$OUTDIR/ownership.tsv" -o "$OUTDIR/ownership.tsv"

# 4. Keep dominated files
awk -F'\t' -v thr="$THRESHOLD" '$1 >= thr' "$OUTDIR/ownership.tsv" \
  | head -n "$MAXFILES" | cut -f4 > "$OUTDIR/owned-files.txt"
OWNED=$(grep -c . "$OUTDIR/owned-files.txt" || true)

# 5. Incremental diff corpus (noise excluded, size-capped)
git log --author="$AUTHOR" --no-merges --since="$SINCE" -p -- "$SCOPE" \
  ':(exclude)**/*.lock' ':(exclude)**/dist/**' ':(exclude)**/build/**' \
  ':(exclude)**/*.snap' ':(exclude)**/*.min.*' 2>/dev/null \
  | head -c 400000 > "$OUTDIR/recent.diff" || true

rm -f "$OUTDIR/.candidates.txt"

cat >&2 <<EOF

>> done. corpus in $OUTDIR/
   owned-files.txt : $OWNED files (>= ${THRESHOLD}% line ownership) — read these in full
   ownership.tsv   : full ranking
   recent.diff     : $(wc -c < "$OUTDIR/recent.diff" | tr -d ' ') bytes of diffs
   commits.txt     : $COMMITS commits
EOF

if [ "$OWNED" -lt 5 ] || [ "$COMMITS" -lt 15 ]; then
  echo ">> WARNING: thin corpus (owned=$OWNED, commits=$COMMITS). Treat the profile as low-confidence." >&2
fi
