---
name: gate-wf
description: Workflow-native quality gate for branch changes — parallel reviewers (Bug, SOLID, Security, Simplify+Slop, optionally React/a11y/i18n/migration) with tier-scaled adversarial verify, CLAUDE.md/ADR enforcement, and a stable PASS / PASS WITH NOTES / FAIL verdict. Read-only. Runs from a static shipped workflow script.
argument-hint: "[base-branch] [--jev] [--force-fresh] [--ignore-scope-gate] [--resume <runId>]"
---

# Gate-WF — Workflow-native quality gate

!IMPORTANT: Follow this process exactly. Do not skip steps.

This skill is a **gate**, not a fixer. It returns a verdict; it does not modify code.

**Skill version**: `10`. v10: `--jev` routes the Verify phase through Jev
(TypeSafe System One) before any skeptic spawns. `jev-verify`'s batch mode
judges each finding over a ±80-line window — one HTTP call per finding, ~$0.042/M
input tokens — and returns keep / kill / escalate. Only the escalate band
(0.50–0.70 defect_real, or Jev saying it needs code outside the window, which is
70% of findings even at ±80) falls back to tier-scaled sonnet skeptics, exactly
as before. A cited rule finding keeps its own resistance floor (kill < 0.10).
Every failure mode — API down, runner relay cut (per-row `msg_len` integrity
check, the v9 lesson applied to the relay), unreadable file, missing row —
routes to a sonnet skeptic: the jev path can only add skeptics, never silently
lose a finding. Without the flag the gate's shape is byte-for-byte unchanged.
Thresholds come from a 125-finding calibration corpus; retune them in
`skills/jev-verify/scripts/jev_verify.py` (KILL_BELOW / KEEP_ABOVE /
KILL_BELOW_CITED), not here. v9: Cache entries are keyed on this — bumping invalidates all caches at once. v9: the report is rendered by `scripts/render.py`, not transcribed by the model. Verdict math, ID assignment, the dismissal partition, refute-vote counts and the `--dismiss`/`--undismiss`/`--show-dismissed` flags all moved out of prose-and-`jq` into Python (`scripts/findings.py`, shared with `triage-findings`) — a model retyping 18 findings by hand was cutting identifiers mid-word (`…INITIATED_POundefined`), mangling badges (`[uns` for `[unverified]`) and truncating the closing tips, and no amount of format spec fixes a transcription problem. The report is now two levels: one scannable line per finding in the terminal, full detail in `$STATE_DIR/<branch>.report.md`. The model's only writing job is a 5-line French summary handed in via `--summary-file`, so it lands above the table instead of below it. v8: `context-checker` infers a rule's normative force from its phrasing instead of keying off MUST/SHOULD — a repo whose rule files are bare imperatives ("Never call `findById` for a document already available in the request pipeline") had its entire rule set produce nothing, and only 5 of 48 files in the case that motivated this mention `MUST` at all. It runs on `opus` with a ≤25-call budget in `MODE: synthesize` (documented-rule enforcement was the cheapest agent in the pipeline while being the most-reported class of review comment) and stays on sonnet for `MODE: annotate`. Discovery reaches `AGENTS.md`, `.claude/CLAUDE.md`, per-directory `AGENTS.md`, and one level of `@`-imports — a repo whose `AGENTS.md` is a one-line pointer had no root `CLAUDE.md` and so no rules at all. An unscoped rule file (no `paths:`) is now applicable to every diff instead of falling through all three strategies. The `## ADR` bundle section names which changed files each rule `binds:`, and a companion ADR contributes its own condensed body rather than inlining the multi-thousand-word record it points at. Synthesized findings go through the same dedup + adversarial verify as reviewer findings — a cited-rule BLOCKER was the only unrefutable finding in the gate and double-counted any line a reviewer already owned — with `agents/skeptic.md` told that a citation-backed finding is refutable only three ways. The ADR freshness fold hashes file contents instead of `git log`: a git-ignored rules dir (`.claude/rules/local/`) never invalidated the cache. v7: `CLAUDE.local.md` at the repo root joins the context bundle alongside `CLAUDE.md`, so a personal, git-ignored rule file reaches `context-checker` and its `MUST`/`SHOULD` clauses synthesize findings. The CLAUDE.md freshness fold now hashes file contents instead of `git log` — a git-ignored rule file has no commit, so the old fold silently no-opped and a rule edit served a stale cached verdict. Also: `adr/` joins `ADR_ROOT_CANDIDATES` and every ADR root is now walked recursively — a repo keeping its ADRs at `adr/`, or its rules in `.claude/rules/<domain>/`, had them read by nothing. Companions that `@`-reference another candidate are deduped. v6: `ponytail-reviewer` greps the repo for an existing equivalent of every export the diff adds (`ponytail-exists`) — duplication of code the repo already has was in no reviewer's scope. v5: `simplify-reviewer` and slop are un-merged into two reviewers (one rule set each), plus a new `ponytail-reviewer` on the over-engineering axis (`/ponytail-review`) — 6 base reviewers instead of 4. Rule ids are unchanged, so existing dismissals survive. v4: each reviewer reads a diff scoped to its concern (code reviewers get docs/snapshots/lockfiles stripped; React/a11y/i18n get a `.tsx/.jsx`-only diff) instead of the full diff — less context noise per agent. v3: the workflow runs from a static shipped script (`scripts/workflow.js`) instead of a model-generated one — deterministic shape, tier-scaled verify, working `--resume`.

## Prerequisites

- Workflows feature enabled: `CLAUDE_CODE_WORKFLOWS=1` in `settings.json` env.
- Plugin installed (this skill ships the reviewer/skeptic/context-checker `agents/*.md` at the plugin root and the orchestration script at `skills/gate-wf/scripts/workflow.js` — see Step 3).

## Arguments

- `$0` (optional): base branch to diff against. If omitted, auto-detect (`main` → `master` → `develop`).
- `--jev` (flag): Jev first pass on the Verify phase (see Step 3e). Requires
  `TYPESAFE_API_KEY` in the env and the `jev-verify` skill reachable; missing
  either fails fast before any reviewer spawns, with the plain skeptic path as
  the documented fallback.
- `--force-fresh` (flag): bypass cache and re-fetch context bundle.
- `--ignore-scope-gate` (flag): downgrade Step 2 hard-stops (file-count, suspicious-files) to top-of-report banners. Soft-warn (1–3 SUSPICIOUS) is unaffected.
- `--resume <runId>`: resume a previous workflow run by ID (`wf_...`). Useful after editing any `agents/*.md` to re-run only the affected agent calls. Resume caches on `(prompt, opts)` pairs — see the resume note in Execution notes for the regeneration caveat.
- `--dismiss <ids>` / `--undismiss <ids>` / `--show-dismissed`: manage the dismissal registry (false-positive suppression) **without running the gate**. See `references/dismissals.md`. These replay from the last run's `$STATE_FILE`; they require a prior run on the branch.

## Step 0: Verify reviewer skill dependencies

Reviewer agents invoke skills via slash-command. A skill is reachable when found in either the global skills dir (`~/.claude/skills/<name>/SKILL.md`) or any plugin cache (`~/.claude/plugins/cache/**/skills/<name>/SKILL.md`). `code-slop` ships with this plugin; the others are external and must be installed globally.

```bash
missing=()
for s in vercel-react-best-practices solid security-review simplify ponytail-review; do
  [ -f ~/.claude/skills/$s/SKILL.md ] && continue
  compgen -G "$HOME/.claude/plugins/cache/*/*/*/skills/$s/SKILL.md" >/dev/null && continue
  missing+=("$s")
done
# code-slop ships in this plugin — probe its in-plugin path
if ! compgen -G "$HOME/.claude/plugins/cache/*/ai-skills/*/skills/code-slop/SKILL.md" >/dev/null \
   && [ ! -f ~/.claude/skills/code-slop/SKILL.md ]; then
  missing+=("code-slop")
fi
if [ ${#missing[@]} -gt 0 ]; then
  printf 'MISS %s\n' "${missing[@]}"
else
  echo "OK all reviewer skills reachable"
fi
```

If any report `MISS`, stop and tell the user which skills are missing. Do not proceed.

| Skill                         | Install                                                                                                             |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `vercel-react-best-practices` | `npx skills add https://github.com/vercel-labs/agent-skills --skill vercel-react-best-practices -g`                 |
| `solid`                       | `npx skills add https://github.com/ramziddin/solid-skills --skill solid -g`                                         |
| `security-review`             | `npx skills add https://github.com/getsentry/skills --skill security-review -g`                                     |
| `code-slop`                   | Ships with this plugin. If missing, reinstall the `bgelis-ai-skills` plugin (`/plugin reinstall bgelis-ai-skills`). |
| `simplify`                    | `npx skills add https://github.com/brianlovin/claude-config --skill simplify -g`                                    |
| `ponytail-review`             | Ships with the `ponytail` plugin — `/plugin install ponytail`.                                                      |

If the project is not React/Next.js, `vercel-react-best-practices` is optional (the react-reviewer is skipped automatically).

**Soft dependencies (context bundle)**: `linear-cli` skill, `gh` CLI, `devsql` CLI. Probe each, degrade gracefully when missing.

**Pre-supposed**: lint, typecheck, and tests have run. The skill does not execute them.

## Step 1: Parse args, compute identifiers, check caches

### 1a. Parse arguments

```bash
ARGS="$@"
BASE_ARG=""
FORCE_FRESH=0
IGNORE_SCOPE_GATE=0
USE_JEV=0
RESUME_ID=""
DISMISS_IDS=""
UNDISMISS_IDS=""
SHOW_DISMISSED=0

# Walk tokens. --resume / --dismiss / --undismiss take the next token as their value.
SKIP_NEXT=0
TOKENS=()
for tok in $ARGS; do TOKENS+=("$tok"); done
for i in "${!TOKENS[@]}"; do
  if [ "$SKIP_NEXT" -eq 1 ]; then SKIP_NEXT=0; continue; fi
  tok="${TOKENS[$i]}"
  case "$tok" in
    --jev)               USE_JEV=1 ;;
    --force-fresh)       FORCE_FRESH=1 ;;
    --ignore-scope-gate) IGNORE_SCOPE_GATE=1 ;;
    --show-dismissed)    SHOW_DISMISSED=1 ;;
    --resume)
      RESUME_ID="${TOKENS[$((i+1))]:-}"
      [ -z "$RESUME_ID" ] && { echo "--resume requires a runId" >&2; exit 2; }
      SKIP_NEXT=1
      ;;
    --dismiss)
      DISMISS_IDS="${TOKENS[$((i+1))]:-}"
      [ -z "$DISMISS_IDS" ] && { echo "--dismiss requires ids (e.g. B1,M2)" >&2; exit 2; }
      SKIP_NEXT=1
      ;;
    --undismiss)
      UNDISMISS_IDS="${TOKENS[$((i+1))]:-}"
      [ -z "$UNDISMISS_IDS" ] && { echo "--undismiss requires ids (e.g. D1,D2)" >&2; exit 2; }
      SKIP_NEXT=1
      ;;
    --*) echo "unknown flag: $tok" >&2; exit 2 ;;
    *)
      [ -z "$BASE_ARG" ] && BASE_ARG="$tok" || { echo "extra positional: $tok" >&2; exit 2; }
      ;;
  esac
done
```

If `--dismiss`, `--undismiss`, or `--show-dismissed` is set, **do not run the gate**. Resolve `render.py` (Step 4) and hand the flag straight to it — it mutates the registry and re-renders from `$STATE_FILE` in one call — then exit:

```bash
python3 "$RENDER" dismiss "$DISMISS_IDS"       # or: undismiss "$UNDISMISS_IDS" / show-dismissed
```

These require a prior run on the branch; the script says so and exits non-zero if `$STATE_FILE` is missing. The re-render carries no `En clair` summary (the finding set barely moved); to refresh it, follow Step 4b–4c.

### 1b. Compute identifiers

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_SLUG=$(echo -n "$REPO_ROOT" | shasum | cut -c1-12)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
BRANCH_SAFE=$(echo "$BRANCH" | tr '/' '_')
SESSION_ID=$(echo -n "${REPO_ROOT}::${BRANCH}" | shasum | cut -c1-12)
TMP_DIR="/tmp/gate-wf-${SESSION_ID}"
mkdir -p "$TMP_DIR"

BASE=${BASE_ARG:-$(git rev-parse --verify main >/dev/null 2>&1 && echo main || (git rev-parse --verify master >/dev/null 2>&1 && echo master || echo develop))}

WRONG_BASE_BANNER=""
if [ -n "$BASE_ARG" ]; then
  case "$BASE_ARG" in
    main|master|develop) ;;
    *) WRONG_BASE_BANNER="Base: ${BASE_ARG} (non-standard — verify this is intentional)" ;;
  esac
fi

HEAD_SHA=$(git rev-parse HEAD)
BASE_SHA=$(git merge-base $BASE HEAD)
# Disable globbing while iterating file paths — Next.js segments like [locale] are
# valid filenames but valid glob patterns too, and unquoted expansion would eat them.
set -f
mapfile -t CHANGED_FILES_ARR < <(git diff $BASE_SHA...HEAD --name-only)
CHANGED_FILES=$(printf '%s\n' "${CHANGED_FILES_ARR[@]}")
WT_HASH=$( {
  git diff HEAD -- "${CHANGED_FILES_ARR[@]}"
  git ls-files --others --exclude-standard -- "${CHANGED_FILES_ARR[@]}" \
    | while IFS= read -r f; do shasum -- "$f" 2>/dev/null; done
} | shasum | cut -c1-12)

# CLAUDE.md and ADR roots — see references/context-sources.md
ADR_ROOT_CANDIDATES=("docs/adr" "adr" "docs/architecture/decisions" ".claude/rules")
ADR_ROOTS=()
for d in "${ADR_ROOT_CANDIDATES[@]}"; do
  [ -d "$REPO_ROOT/$d" ] && ADR_ROOTS+=("$d")
done

# Root instruction files. AGENTS.md and .claude/CLAUDE.md are as canonical as CLAUDE.md and were
# read by nothing — a repo whose AGENTS.md is one line ("Follow @.claude/CLAUDE.md") had its
# entire rule set invisible to the gate.
ROOT_RULE_FILES=("CLAUDE.md" "CLAUDE.local.md" "AGENTS.md" ".claude/CLAUDE.md")
CLAUDE_MD_LIST=$( {
  for r in "${ROOT_RULE_FILES[@]}"; do [ -f "$REPO_ROOT/$r" ] && echo "$REPO_ROOT/$r"; done
  for f in "${CHANGED_FILES_ARR[@]}"; do
    dir=$(dirname -- "$f")
    while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
      [ -f "$REPO_ROOT/$dir/CLAUDE.md" ] && echo "$REPO_ROOT/$dir/CLAUDE.md"
      [ -f "$REPO_ROOT/$dir/AGENTS.md" ] && echo "$REPO_ROOT/$dir/AGENTS.md"
      dir=$(dirname -- "$dir")
    done
  done
} | sort -u)

# One level of @-import resolution: a pointer file's targets are rule files too. Only .md targets
# — a directory import (@adr/, @docs/) is ADR discovery's job, and recursing past one level pulls
# the whole doc tree into the bundle.
CLAUDE_MD_LIST=$( {
  printf '%s\n' "$CLAUDE_MD_LIST"
  printf '%s\n' "$CLAUDE_MD_LIST" | while IFS= read -r f; do
    [ -n "$f" ] && grep -ohE '@[A-Za-z0-9._/-]+\.md' -- "$f" 2>/dev/null
  done | sed 's|^@||' | sort -u | while IFS= read -r rel; do
    if [ -n "$rel" ] && [ -f "$REPO_ROOT/$rel" ]; then
      # Skip imports landing under an ADR root: already discovered there, with `paths:`
      # applicability on top. Inlining them here too duplicates them verbatim in the bundle.
      in_adr=0
      for d in "${ADR_ROOTS[@]}"; do
        [ "${rel#$d/}" != "$rel" ] && in_adr=1
      done
      [ $in_adr -eq 0 ] && echo "$REPO_ROOT/$rel"
    fi
  done
} | sed '/^$/d' | sort -u)
set +f

if [ -n "$CLAUDE_MD_LIST" ]; then
  # Content hash, not `git log`: CLAUDE.local.md is git-ignored in most repos, so a
  # git-log fold silently no-ops and a rule edit serves a stale cached verdict. Hashing
  # the bytes works tracked or not, and additionally catches uncommitted edits.
  # Read line by line rather than unquoted `cat -- $LIST`: zsh does not word-split an
  # unquoted expansion, so the whole list would arrive as one bogus path, cat would fail,
  # and the hash would be sha("") on every run — a cache that never invalidates.
  CLAUDE_MD_GIT_SHA=$(printf '%s\n' "$CLAUDE_MD_LIST" | while IFS= read -r f; do
    [ -n "$f" ] && cat -- "$f"
  done | shasum | cut -c1-12)
  WT_HASH=$(echo "${WT_HASH} ${CLAUDE_MD_GIT_SHA}" | shasum | cut -c1-12)
fi
if [ ${#ADR_ROOTS[@]} -gt 0 ]; then
  # Content hash, not `git log` — same bug class the CLAUDE.md fold hit in v7. A rules dir can be
  # git-ignored (`.claude/rules/local/`) or edited without committing; a git-log fold then silently
  # no-ops and a rule edit serves a stale cached verdict. Name kept as ADR_GIT_SHA: the Step 1d
  # probe and freshness_signals.adr_git_sha both read it.
  ADR_GIT_SHA=$(find "${ADR_ROOTS[@]/#/$REPO_ROOT/}" -name '*.md' -type f -print0 2>/dev/null \
    | sort -z | xargs -0 shasum 2>/dev/null | shasum | cut -c1-12)
  [ -n "$ADR_GIT_SHA" ] && WT_HASH=$(echo "${WT_HASH} ${ADR_GIT_SHA}" | shasum | cut -c1-12)
fi

CACHE_KEY="${HEAD_SHA}_${BASE_SHA}_${WT_HASH}_v5"
STATE_DIR="$HOME/.claude/gate-wf-state/$REPO_SLUG"
STATE_FILE="$STATE_DIR/${BRANCH_SAFE}.json"
CONTEXT_CACHE_FILE="$STATE_DIR/${BRANCH_SAFE}.context.json"
# Dismissal registry — false-positive suppression, kept OUTSIDE CACHE_KEY so a
# rejected finding stays suppressed across diff churn. See references/dismissals.md.
DISMISS_FILE="$STATE_DIR/${BRANCH_SAFE}.dismissed.json"
mkdir -p "$STATE_DIR"
[ -f "$DISMISS_FILE" ] || echo '{"version":1,"dismissals":[]}' > "$DISMISS_FILE"
```

### 1c. Findings cache lookup

If `FORCE_FRESH=0` and `RESUME_ID=""`:

1. Read `$STATE_FILE`.
2. If `cache_key == CACHE_KEY` AND `cached_at` is within 7 days, **cache hit**: skip the workflow and skip Step 4a (`ingest`) — go straight to Step 4b (`brief`) and 4c (`show`). Both re-partition against the registry before printing, so a dismissal added since the cached run (via `--dismiss`, or a newly-resolved thread) applies even though `CACHE_KEY` is unchanged. Then exit.
3. Otherwise: cache miss, proceed.

`CACHE_KEY` includes `WT_HASH`, so any working-tree change invalidates the cache.

### 1d. Context bundle freshness probes

Skip probes when `FORCE_FRESH=1`. Otherwise, run all 4 probes in parallel:

1. **Linear**: extract ticket ID `[A-Z]+-[0-9]+` from branch name. If found, query `updatedAt` via `linear-cli`.
2. **GitHub PR**: `gh pr view --json updatedAt` for current branch.
3. **ADR**: reuse `ADR_GIT_SHA` from Step 1b.
4. **CLAUDE.md**: reuse `CLAUDE_MD_GIT_SHA` from Step 1b.
5. **devsql**: per changed file, `MAX(timestamp)` from `history` and `jhistory` tables.

Compare to cached `freshness_signals` in `$CONTEXT_CACHE_FILE`. For each source:

| Cached vs Fresh             | Action                                  |
| --------------------------- | --------------------------------------- |
| equal                       | **reuse** cached portion                |
| different                   | **re-fetch**                            |
| cached null, fresh not null | **fetch**                               |
| cached not null, fresh null | **re-fetch** (transient unavailability) |
| no cache file               | **fetch all**                           |

### 1e. Assemble context bundle (bash)

For each stale source, fetch:

- **Linear** (if stale + ticket detected): `linear-cli` issue + comments. See `references/context-sources.md`.
- **GitHub PR** (if stale): `gh pr view --json number,title,body,comments,reviews,updatedAt`, **plus inline review threads** — the signal the author uses to reject a finding. `gh pr view --json` omits thread `isResolved`/comments, so fetch them via GraphQL (same query the `pr-feedback` skill uses):

  ```bash
  gh api graphql -f query='query($owner:String!,$repo:String!,$pr:Int!){
    repository(owner:$owner,name:$repo){ pullRequest(number:$pr){
      reviewThreads(first:100){ nodes{ isResolved isOutdated
        comments(first:10){ nodes{ author{login} body path line originalLine } } } } } }
  }' -F owner=OWNER -F repo=REPO -F pr=<n>
  ```

  Emit these under a `### Review threads` subsection of the `## PR` bundle section (one entry per thread: `isResolved`, `path`, `line`, and each comment's `author` + `body`). The context-checker reads this to dismiss findings the author rejected (see `references/dismissals.md` and `agents/context-checker.md` Part 3). Resolving a thread bumps the PR `updatedAt`, so this rides the existing PR freshness probe — no new probe needed.

- **ADR** (if stale): walk `ADR_ROOTS`, determine applicability — an unscoped rule (no `paths:`) is global, otherwise frontmatter `paths:` glob, filename keyword match, or body mention. Emit each applicable rule with its `description:` and a `binds:` line naming the changed files it covers. See `references/context-sources.md` § F3.
- **CLAUDE.md** (if stale): emit each `$CLAUDE_MD_LIST` file verbatim under a `### <path>` heading — the list covers `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, `.claude/CLAUDE.md`, per-directory `CLAUDE.md`/`AGENTS.md`, and one level of `@`-imports. See `references/context-sources.md` § F2.
- **devsql** (if stale): per changed file, last 10 history/jhistory rows. Cap at 80 total.

Merge fetched + cached portions into `$TMP_DIR/context-bundle.md` with the section headers from `references/context-sources.md`. Write the new freshness signals to `$TMP_DIR/freshness-signals.json`.

## Step 2: Get diff, detect stack, scope-gate

### 2a. Diff

```bash
git diff $BASE_SHA...HEAD --name-only > "$TMP_DIR/diff-summary.txt"
git diff $BASE_SHA...HEAD              > "$TMP_DIR/diff-full.txt"

# Diff stats for the report header (Step 4a). --shortstat over parsing the diff.
read -r DIFF_FILES DIFF_ADD DIFF_DEL <<<"$(git diff $BASE_SHA...HEAD --shortstat \
  | awk '{f=0;a=0;d=0; for(i=1;i<NF;i++){ if($(i+1)~/^file/) f=$i;
      else if($(i+1)~/^insertion/) a=$i; else if($(i+1)~/^deletion/) d=$i }
      print f+0, a+0, d+0}')"
DIFF_FILES=${DIFF_FILES:-0}; DIFF_ADD=${DIFF_ADD:-0}; DIFF_DEL=${DIFF_DEL:-0}

# plus-lines: `+` lines per file. Reused for every scoped variant below.
plus_lines() {  # $1 = diff file → stdout
  awk '
    /^diff --git/ { f=$3; sub(/^a\//,"",f) }
    /^\+\+\+/ { f=substr($2,3) }
    /^\+/ && !/^\+\+\+/ { print f": "substr($0,2) }
  ' "$1"
}

# Scoped diffs: each reviewer reads only the slice it can act on, so docs/snapshots/
# lockfiles never fill a code reviewer's context and the JSX reviewers see only .tsx/.jsx.
# diff-full.txt stays for the context-checker (it walks everything against CLAUDE.md/ADR).
# ponytail: pathspec excludes are the noise floor, not a security boundary.
# Leading '.' anchors the include set; :(exclude,glob) so **/ also matches root-level
# files (a bare **/ won't match zero dirs, so a root pnpm-lock.yaml would leak).
CODE_EXCLUDES=(
  '.'
  ':(exclude,glob)**/*.md'
  ':(exclude,glob)**/*.snap' ':(exclude,glob)**/__snapshots__/**'
  ':(exclude,glob)**/*.lock' ':(exclude,glob)**/*-lock.json'
  ':(exclude,glob)**/*.lockb' ':(exclude,glob)**/pnpm-lock.yaml'
  ':(exclude,glob)docs/**'
)
set -f
git diff $BASE_SHA...HEAD -- "${CODE_EXCLUDES[@]}" > "$TMP_DIR/diff-code.txt"
git diff $BASE_SHA...HEAD -- '*.tsx' '*.jsx'        > "$TMP_DIR/diff-tsx.txt"
set +f

plus_lines "$TMP_DIR/diff-code.txt" > "$TMP_DIR/diff-code-plus.txt"
plus_lines "$TMP_DIR/diff-tsx.txt"  > "$TMP_DIR/diff-tsx-plus.txt"
```

The workflow (`scripts/workflow.js`) maps each reviewer to its diff: the JSX reviewers
(`react`, `a11y`, `i18n`) read `diff-tsx*`; every other reviewer reads `diff-code*`; the
context-checker's CLAUDE.md/ADR synthesis reads `diff-full.txt`.

### 2b. Conditional reviewer flags

```bash
# react: package.json deps
SPAWN_REACT=0
if jq -r '.dependencies // {} | keys[]' package.json 2>/dev/null | grep -qE '^(react|next)$'; then
  SPAWN_REACT=1
fi

# migration
SPAWN_MIGRATION=0
MIGRATION_PATHS=$(echo "$CHANGED_FILES" | grep -E '(migrations/|.*migration.*\.ts$|.*\.migration\.ts$)' | grep -vE '(test|spec|fixture|__mocks__)' || true)
if [ -n "$MIGRATION_PATHS" ]; then
  SPAWN_MIGRATION=1
elif git diff $BASE_SHA...HEAD -- $CHANGED_FILES | grep -E '(updateMany|bulkWrite|deleteMany)' | grep -vE '(test|spec|fixture|__mocks__)' >/dev/null 2>&1; then
  SPAWN_MIGRATION=1
fi

# a11y / i18n
SPAWN_A11Y=0
SPAWN_I18N=0
echo "$CHANGED_FILES" | grep -qE '\.(tsx|jsx)$' && SPAWN_A11Y=1
if [ "$SPAWN_A11Y" -eq 1 ] && jq -r '.dependencies // {}, .devDependencies // {} | keys[]' package.json 2>/dev/null | grep -qE '^(react-intl|next-intl|formatjs|i18next)$'; then
  SPAWN_I18N=1
fi
```

### 2c. Scope-gate

Full spec: `references/scope-gate.md`. Hard-stops here `exit 0` directly — they do NOT invoke the workflow.

**File-count hard-stop** (>200 files): emit the banner from `references/scope-gate.md`, exit unless `--ignore-scope-gate` (in which case, set `FILE_COUNT_BANNER` and continue).

**Suspicious-files classifier**:

- Skip if `FILE_COUNT <= 1`.
- Determine intent (Linear title/body → PR title/body → last commit → branch name).
- Run the Haiku classifier (single Agent call, read-only, model: haiku) — cache its result at `$STATE_DIR/${BRANCH_SAFE}.scope.json` keyed on SHA-12 of `CHANGED_FILES`.
- Decision: 0 SUSPICIOUS → silent. 1–3 → `SUSPICIOUS_BANNER` (soft-warn). ≥4 → hard-stop unless `--ignore-scope-gate`.

## Step 3: Run the gate workflow

The orchestration lives in a static script shipped with the plugin
(`skills/gate-wf/scripts/workflow.js`). The skill resolves its path, invokes it via the
`Workflow` tool, and gets back `{ findings: [...] }`. The shape is fixed in code —
parallel reviewers → tier-scaled adversarial verify (BLOCKER→3 skeptics, MAJOR→1, NIT→0)
with per-`(file,line)` dedup → single context annotation, with CLAUDE.md/ADR synthesis
running alongside the reviewers. No model-generated script, so the shape can't drift and
`--resume` caches reliably.

### 3a. Prepare flag-conditional reviewer list

```bash
# One reviewer per rule set (v5): simplify=/simplify, slop=/ai-skills:code-slop,
# ponytail=/ponytail-review. None of the three can emit BLOCKER.
REVIEWERS=(
  "ai-skills:bug-reviewer"
  "ai-skills:solid-reviewer"
  "ai-skills:security-reviewer"
  "ai-skills:simplify-reviewer"
  "ai-skills:slop-reviewer"
  "ai-skills:ponytail-reviewer"
)
[ $SPAWN_REACT -eq 1 ]     && REVIEWERS+=("ai-skills:react-reviewer")
[ $SPAWN_A11Y -eq 1 ]      && REVIEWERS+=("ai-skills:a11y-reviewer")
[ $SPAWN_I18N -eq 1 ]      && REVIEWERS+=("ai-skills:i18n-reviewer")
[ $SPAWN_MIGRATION -eq 1 ] && REVIEWERS+=("ai-skills:migration-reviewer")

# JSON array for the workflow's args.reviewers
REVIEWERS_JSON=$(printf '%s\n' "${REVIEWERS[@]}" | jq -R . | jq -sc .)
```

### 3b. Resolve the workflow script

The script ships with the plugin. Resolve its path (plugin-root env → newest plugin
cache → global-skills fallback):

```bash
WF_SCRIPT=""
for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/gate-wf/scripts/workflow.js}" \
         $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/gate-wf/scripts/workflow.js 2>/dev/null | sort -V | tail -1) \
         "$HOME/.claude/skills/gate-wf/scripts/workflow.js"; do
  [ -n "$c" ] && [ -f "$c" ] && WF_SCRIPT="$c" && break
done
[ -z "$WF_SCRIPT" ] && { echo "gate-wf: workflow.js not found — reinstall the plugin" >&2; exit 2; }
```

### 3c. Invoke and capture result

Invoke the `Workflow` tool with the resolved script and the run args:

```
Workflow({
  scriptPath: <WF_SCRIPT>,
  args: {
    tmpDir:   "<TMP_DIR>",
    reviewers: <REVIEWERS_JSON>,   // e.g. ["ai-skills:bug-reviewer", ...]
    prNumber:  <PR number or null>,
    useJev:    <true when --jev, else omit>,
    jevScript: <$JV from Step 3e when --jev, else omit>
  }
})
```

Pass `args` as a real JSON object (not a stringified blob). The script defensively
normalizes a JSON-stringified `args` too, but the object form is canonical.

The script assembles its own agent prompts from `args` (the per-finding schema, the
read-scope/finding-scope and Boy-Scout constraints, the skeptic and context-checker
modes all live in `scripts/workflow.js` and the `agents/*.md` system prompts). It returns
`{ findings: [...] }` where each finding already carries `verifications[]`,
`context_verdict`/`context_source`/`context_citation`/`context_reason` (and
`dismiss_confidence` when DISMISSED), `reviewer`, and `also_flagged_by` for deduped
duplicates. Synthesized `claude-md-violation`/`adr-violation` findings carry
`reviewer: "context-checker"` plus `citation`/`source`, and go through the same
tier-scaled verify and `(file,line)` dedup as reviewer findings — so they carry real
`verifications[]`. When a synthesized finding lands on a line a reviewer already claimed,
the citation-backed tier wins: the primary is promoted and the rule finding merges in as
`also_flagged_by`.

After the run, capture the `runId` from `/workflows` (task panel) into `RUN_ID`, and write
the returned `findings` array verbatim to `$TMP_DIR/findings.json`. Both feed Step 4a.
`PR_NUMBER` is the PR number resolved in Step 1d, or empty when the branch has no PR.

To re-run after editing an `agents/*.md`, invoke `Workflow({scriptPath: <WF_SCRIPT>,
resumeFromRunId: <runId>})` (same session) — unchanged agent calls return cached results;
only the edited agent's calls re-run.

### 3d. Failure modes

- **Workflows disabled** (`disableWorkflows=true`, or `CLAUDE_CODE_WORKFLOWS` unset): the
  `Workflow` tool errors. Surface it and exit — the skill cannot proceed.
- **Reviewer agent type not found**: the workflow surfaces a per-agent error. Verify
  Step 0 dependencies passed and the plugin is loaded.

### 3e. `--jev` — Jev first pass on Verify (Step 3c runs with `useJev: true`)

Prerequisites, checked **before** the Workflow invocation (fail fast, before any
reviewer spends tokens):

```bash
if [ $USE_JEV -eq 1 ]; then
  [ -n "$TYPESAFE_API_KEY" ] || { echo "gate-wf: --jev needs TYPESAFE_API_KEY (console.typesafe.ai) — unset it or drop --jev" >&2; exit 2; }
  JV=""
  for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/skills/jev-verify/scripts/jev_verify.py}"            $(ls -1 "$HOME"/.claude/plugins/cache/*/ai-skills/*/skills/jev-verify/scripts/jev_verify.py 2>/dev/null | sort -V | tail -1)            "$HOME/.claude/skills/jev-verify/scripts/jev_verify.py"; do
    [ -n "$c" ] && [ -f "$c" ] && JV="$c" && break
  done
  [ -z "$JV" ] && { echo "gate-wf: --jev needs the jev-verify skill — /plugin reinstall bgelis-ai-skills, or drop --jev" >&2; exit 2; }
  # Credit check. The API exposes no balance endpoint, so the only proof of
  # credit is a served call: one ~300-token probe (~$0.00001). Doing this here
  # is the point — fail before the reviewers spend anything, not mid-Verify.
  python3 "$JV" preflight || \
    { echo "gate-wf: --jev preflight failed — fix the key/credit, or drop --jev for plain skeptics" >&2; exit 2; }
fi
```

What the workflow does with `useJev: true` (all in `scripts/workflow.js`, nothing for
the model to operate):

1. After each reviewer's findings, the BLOCKER/MAJOR survivors are handed to
   `jev_verify.py batch` via a haiku `jev-runner` agent (the workflow sandbox has no
   network; python does the HTTP, the runner only relays its stdout).
2. Per row the workflow checks `msg_len` against the original finding — the v9
   transcription lesson: a relay that cut a message mid-word is untrusted and its
   finding goes to a skeptic.
3. Routing: `keep` → finding survives with a `jev first pass` verification entry;
   `kill` → finding dies; `escalate` (the 0.50–0.70 band, `needs_wider_context`, or
   any failure: API down, unreadable file, chunk lost) → the tier-scaled sonnet
   skeptics run exactly as without the flag.
4. NIT findings are unaffected (they were never verified). Cited
   `claude-md-violation`/`adr-violation` findings keep their resistance floor.

Skeptics a `--jev` run spawns ≈ findings in the escalate band, vs all BLOCKER×3 +
MAJOR×1 without it. On the calibration corpus that was ~35% of findings reaching a
skeptic. The verdict math, dedup, and rendering are untouched — a `--jev` run
produces the same report shape with fewer skeptic agents behind it.
- **`workflow.js` not found**: Step 3b exits — reinstall the plugin.

## Step 4: Render the report

Everything deterministic — the active/dismissed partition, verdict math, ID
assignment, refute-vote counts, both outputs — is done by `scripts/render.py`.
Do not compute or transcribe any of it by hand: a model retyping a finding set
truncates lines mid-word and drops fields, which is exactly the failure this
step was written to remove.

Resolve the script next to `workflow.js` (same plugin-root → cache → global
fallback as Step 3b), then:

```bash
RENDER="$(dirname "$WF_SCRIPT")/render.py"
```

### 4a. Ingest the workflow result

Write the workflow's `findings` array to `$TMP_DIR/findings.json` verbatim (no
edits, no re-ordering), then:

```bash
python3 "$RENDER" ingest \
  --findings "$TMP_DIR/findings.json" \
  --run-id "$RUN_ID" --cache-key "$CACHE_KEY" \
  --files "$DIFF_FILES" --add "$DIFF_ADD" --del "$DIFF_DEL" \
  --base-banner "$WRONG_BASE_BANNER" ${PR_NUMBER:+--pr "$PR_NUMBER"}
```

`ingest` writes `$STATE_FILE` (Step 5a is done — nothing else writes it),
upserts any context-checker `DISMISSED` annotation into the registry, partitions
active vs dismissed against the content anchors, assigns `B1/M1/N1/D1` ids, and
computes the verdict.

`WRONG_BASE_BANNER` is empty on a standard base, and the renderer prints nothing
when it is empty. `FILE_COUNT_BANNER` and `SUSPICIOUS_BANNER` (Step 2c), when
non-empty, are printed by you verbatim **before** the render output.

### 4b. Write the summary

```bash
python3 "$RENDER" brief
```

This prints one compact line per finding — id, tier, rule, location, message,
without `evidence`/`suggested_fix`/`citation`. Read it, then write a summary to
`$TMP_DIR/summary.md`:

- **In French**, at most 5 lines, no heading (the renderer adds `En clair`).
- Three things in order: what blocks, what deserves a real look, what is cleanup.
- Name findings by id (`B1`, `M1 et M2`, `les 9 NIT`).
- Say what a finding *means*, not what tier it has — the table already shows the tier.
- Where two findings contradict each other, or a finding is a code/spec
  disagreement only the author can settle, say so.

Example, for the run rendered in the sample above:

```
B1 — trois `?? 0` interdits par packages/wome-api/CLAUDE.md:38 ; un document sans total devient un total de 0 €. À corriger.
M1 et M2 sont les deux vrais bugs. M2 est peut-être la spec qui a bougé — à toi de dire lequel est faux.
Les 9 NIT sont du ménage : /triage-findings nits.
```

### 4c. Print it

```bash
python3 "$RENDER" show --summary-file "$TMP_DIR/summary.md"
```

Emit the script's stdout as-is. Do not re-format it, do not re-list findings
under it, do not append a prose recap — the summary you just wrote is the recap,
and it is already at the top.

The report has two levels by design. The terminal gets the verdict, the summary,
the tier counts and **one line per finding** (`id`, tier, `basename:line`,
`rule_id`, message clipped with an explicit `…`, plus `!` for a context conflict
and `?` for an unverified finding). Full detail — evidence, fix, citation,
refute votes, full paths, the dismissed section — goes to
`$STATE_DIR/${BRANCH_SAFE}.report.md`, whose path is the last line before the
tips. On a PASS with no findings the whole report is three lines.

## Step 5: Persist state

### 5a. Findings cache

Already written — `render.py ingest` (Step 4a) owns `$STATE_FILE`, and every
`show`/`dismiss`/`undismiss` rewrites it after re-partitioning. Nothing to do
here.

Its shape, for readers (`triage-findings` and `pr-comment` consume it):

```json
{
  "cache_key": "<CACHE_KEY>",
  "cached_at": "<ISO timestamp>",
  "verdict": "PASS | PASS WITH NOTES | FAIL",
  "run_id": "<wf_...>",
  "pr": "<number or empty>",
  "diff": { "files": 12, "add": 998, "del": 3 },
  "base_banner": "<banner or empty>",
  "findings": [ { "id": "B1", ... }, ... ],
  "dismissed": [ { "id": "D1", "anchor": "<sha>", "source": "pr-thread|manual", "confidence": "resolved|rebutted|manual", "citation": "...", ... full finding payload ... }, ... ]
}
```

`dismissed[]` carries each suppressed finding's full payload plus its `anchor`/`source`/`confidence`/`citation`, so `--undismiss` can promote it back and a cache-hit replay can re-partition without re-running the gate. The registry itself (`$DISMISS_FILE`) is the source of truth for _what_ is dismissed; `dismissed[]` is the last-rendered snapshot.

### 5b. Context bundle cache

Write `$CONTEXT_CACHE_FILE`:

```json
{
  "key": "<BRANCH_SAFE>_v3",
  "fetched_at": "<ISO timestamp>",
  "freshness_signals": { ... from $TMP_DIR/freshness-signals.json ... },
  "bundle_sources": {
    "linear":    "<verbatim ## Linear section>" | null,
    "pr":        "<verbatim ## PR section>" | null,
    "adr":       "<verbatim ## ADR section>" | null,
    "claude_md": "<verbatim ## CLAUDE.md section>" | null,
    "sessions":  "<verbatim ## Past Claude Code sessions section>" | null
  }
}
```

Reused-from-cache portions stay as-is.

### 5c. Cleanup

```bash
rm -rf "$TMP_DIR"
# GC orphan dirs older than 24h
find /tmp -maxdepth 1 -type d -name 'gate-wf-*' -mmin +1440 -print 2>/dev/null \
  | while read -r d; do
      [ "$d" != "$TMP_DIR" ] && rm -rf "$d"
    done

# GC orphan dismissal registries: a <branch>.dismissed.json whose branch no longer
# exists AND has no sibling <branch>.json is dead — remove it.
# ponytail: branch reconstruction (tr '_' '/') is lossy for branches with literal
# underscores; the sibling-.json guard keeps any still-active registry safe.
for f in "$STATE_DIR"/*.dismissed.json; do
  [ -e "$f" ] || continue
  b=$(basename "$f" .dismissed.json)
  [ -f "$STATE_DIR/$b.json" ] && continue
  git show-ref --verify --quiet "refs/heads/$(echo "$b" | tr '_' '/')" \
    || rm -f "$f" "$STATE_DIR/$b.report.md"
done
```

## Execution notes

- **Requires**: `CLAUDE_CODE_WORKFLOWS=1` in `settings.json`.
- **Static script**: the orchestration is `scripts/workflow.js` (shipped with the plugin), invoked via `Workflow({scriptPath, args})`. It is NOT model-generated, so the shape is fixed run-to-run — no drift (double context-checker, stray extra reviewers), and `--resume` caches reliably.
- **Pipeline shape**: the script uses `pipeline()` over reviewers — each reviewer's findings stream into per-finding verify the moment its review returns. No barrier between review and verify. CLAUDE.md/ADR synthesis (`context-checker` in `MODE: synthesize`) runs alongside the reviewers, then its findings go through the same verify round; the single annotation pass (`MODE: annotate`) runs once at the end over every survivor, synthesized ones included, so a PR-thread rejection can dismiss a rule violation. Annotate is `(file,line,rule_id)` matching, not investigation, so the script pins it to sonnet while `synthesize` runs on the agent's own model.
- **Tier-scaled verify**: BLOCKER → 3 independent skeptics (drop if ≥2 refute), MAJOR → 1 skeptic (drop if it refutes), NIT → 0 (shown, unverified — NITs never affect the verdict, so verifying them was pure cost). Skeptics are refute-prompted (default refuted=true if uncertain) with a ≤6 tool-call budget.
- **Dedup**: findings are claimed per `(file,line)`; the first reviewer to claim a line owns it, later duplicates merge in as `also_flagged_by` without spawning their own skeptics. Exception: a citation-backed finding (`claude-md-violation`/`adr-violation`) promotes the primary's tier when it is higher — a NIT that claimed the line first must not swallow a documented-rule BLOCKER. The promoted finding keeps the votes it earned at its old tier, so it can render `[refute votes: K/1]` at BLOCKER.
- **Concurrency cap**: workflow runtime caps at 16 parallel agents. Reviewers + skeptics beyond that queue automatically.
- **No `Date.now()`/`Math.random()` in the workflow**: all timestamps are stamped in this skill (bash + post-workflow). The script is deterministic so resume works.
- **Resume**: `--resume <runId>` → `Workflow({scriptPath, resumeFromRunId})`. Same session, same args → unchanged `agent()` calls return cached results; editing one `agents/*.md` re-runs only that agent's calls.
- **Boy Scout asymmetry**: adjacent legacy code can be flagged (MAJOR/NIT) but never blocks the gate.
- **Tier semantics**: only BLOCKER affects the verdict. MAJOR and NIT are informational.
- **Dismissals**: false-positives are suppressed via a per-branch registry kept _outside_ `CACHE_KEY` (`references/dismissals.md`). Suppression is keyed on the offending code's text (a content-anchor), so it survives diff churn but lifts the moment the code is edited. Two populators: PR review threads the author resolved (auto, via the context-checker) and `--dismiss <ids>` (manual). Dismissed findings are excluded from `findings[]` — so `pr-comment` never re-posts them — and from the verdict, but always shown in a `Dismissed (N)` section. This is what stops a blocker the author marked false-positive from being re-posted indefinitely.
- **No auto-fix**: this skill is read-only review. Acting on findings is `triage-findings`, which reads the same `$STATE_FILE` through `scripts/findings.py`.
- **Rendering is code, not prose**: `scripts/render.py` owns the verdict, the ids, the partition and both outputs. Never recompute or re-list any of it by hand. `scripts/test_render.py` is its self-check (`python3 scripts/test_render.py`); the anchor test pins byte-compatibility with the bash implementation it replaced, so existing dismissal registries keep matching.
- **Coexists** with the legacy `gate` skill during migration.

## References

- `references/context-sources.md` — CLAUDE.md (F2) + ADR (F3) discovery and enforcement
- `references/scope-gate.md` — file-count + suspicious-files classifier (Step 2c)
- `references/dismissals.md` — dismissal registry: content-anchor identity, PR-thread + manual populators, render core, `--dismiss`/`--undismiss`/`--show-dismissed`
- `scripts/render.py` — report renderer + registry CLI (`ingest`, `brief`, `show`, `dismiss`, `undismiss`, `show-dismissed`)
- `scripts/findings.py` — state access, content anchors, partition, verdict, ids, selectors (shared with `triage-findings`)
