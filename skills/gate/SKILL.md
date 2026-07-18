---
name: gate
description: Harness-portable quality gate for branch changes — spawns parallel reviewer subagents (Bug, SOLID, Security, Simplify+Slop, optionally React/a11y/i18n/migration) with tier-scaled adversarial verify, CLAUDE.md/ADR enforcement, and a stable PASS / PASS WITH NOTES / FAIL verdict. Read-only. Runs on any harness with a subagent primitive (Claude Code, Codex) — no Workflow tool, no agent teams.
argument-hint: "[base-branch] [--force-fresh] [--ignore-scope-gate] [--dismiss <ids>] [--undismiss <ids>] [--show-dismissed]"
---

# Gate — harness-portable quality gate

!IMPORTANT: Follow this process exactly. Do not skip steps.

This skill is a **gate**, not a fixer. It returns a verdict; it does not modify code.

It orchestrates with a single primitive every agent harness has: **spawn a subagent, read its result**. No Workflow tool, no agent teams — so it runs unchanged on Claude Code and Codex. The companion `gate-wf` skill runs the same review logic on the Claude Code `Workflow` engine (deterministic static script, `--resume` caching); prefer it when Workflows are enabled.

**Skill version**: `5`. Cache entries are keyed on this — bumping invalidates all caches at once.

## Prerequisites

- A harness with a subagent primitive (Claude Code `Agent`/`Task` tool, Codex subagents). Reviewer subagent types (`bug-reviewer`, `solid-reviewer`, … `skeptic`, `context-checker`) ship with this plugin at the plugin root `agents/*.md` — they are the single source of the review logic, shared with `gate-wf`.
- The reviewer skill dependencies of Step 0.

## Arguments

- `$0` (optional): base branch to diff against. If omitted, auto-detect (`main` → `master` → `develop`).
- `--force-fresh` (flag): bypass cache and re-fetch context bundle.
- `--ignore-scope-gate` (flag): downgrade Step 2 hard-stops (file-count, suspicious-files) to top-of-report banners. Soft-warn (1–3 SUSPICIOUS) is unaffected.
- `--dismiss <ids>` / `--undismiss <ids>` / `--show-dismissed`: manage the dismissal registry (false-positive suppression) **without running the gate**. See `references/dismissals.md`. These replay from the last run's `$STATE_FILE`; they require a prior run on the branch.

## Step 0: Verify reviewer skill dependencies

Reviewer subagents invoke skills via slash-command. A skill is reachable when found in either the global skills dir (`~/.claude/skills/<name>/SKILL.md`) or any plugin cache (`~/.claude/plugins/cache/**/skills/<name>/SKILL.md`). `code-slop` ships with this plugin; the others are external and must be installed globally.

```bash
missing=()
for s in vercel-react-best-practices solid security-review simplify; do
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
DISMISS_IDS=""
UNDISMISS_IDS=""
SHOW_DISMISSED=0

# Walk tokens. --dismiss / --undismiss take the next token as their value.
SKIP_NEXT=0
TOKENS=()
for tok in $ARGS; do TOKENS+=("$tok"); done
for i in "${!TOKENS[@]}"; do
  if [ "$SKIP_NEXT" -eq 1 ]; then SKIP_NEXT=0; continue; fi
  tok="${TOKENS[$i]}"
  case "$tok" in
    --force-fresh)       FORCE_FRESH=1 ;;
    --ignore-scope-gate) IGNORE_SCOPE_GATE=1 ;;
    --show-dismissed)    SHOW_DISMISSED=1 ;;
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

If `--dismiss`, `--undismiss`, or `--show-dismissed` is set, **do not run the gate** — after computing identifiers (Step 1b, for `$STATE_DIR` / `$STATE_FILE` / `$DISMISS_FILE`), jump straight to the manual-flag handling in `references/dismissals.md` (Manual flags), then Step 4 render, then exit.

### 1b. Compute identifiers

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_SLUG=$(echo -n "$REPO_ROOT" | shasum | cut -c1-12)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
BRANCH_SAFE=$(echo "$BRANCH" | tr '/' '_')
SESSION_ID=$(echo -n "${REPO_ROOT}::${BRANCH}" | shasum | cut -c1-12)
TMP_DIR="/tmp/gate-${SESSION_ID}"
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
ADR_ROOT_CANDIDATES=("docs/adr" "docs/architecture/decisions" ".claude/rules")
ADR_ROOTS=()
for d in "${ADR_ROOT_CANDIDATES[@]}"; do
  [ -d "$REPO_ROOT/$d" ] && ADR_ROOTS+=("$d")
done

CLAUDE_MD_LIST=$( {
  [ -f "$REPO_ROOT/CLAUDE.md" ] && echo "$REPO_ROOT/CLAUDE.md"
  for f in "${CHANGED_FILES_ARR[@]}"; do
    dir=$(dirname -- "$f")
    while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
      [ -f "$REPO_ROOT/$dir/CLAUDE.md" ] && echo "$REPO_ROOT/$dir/CLAUDE.md"
      dir=$(dirname -- "$dir")
    done
  done
} | sort -u)
set +f

if [ -n "$CLAUDE_MD_LIST" ]; then
  CLAUDE_MD_GIT_SHA=$(git log -1 --format=%H -- $CLAUDE_MD_LIST 2>/dev/null | cut -c1-12)
  WT_HASH=$(echo "${WT_HASH} ${CLAUDE_MD_GIT_SHA}" | shasum | cut -c1-12)
fi
if [ ${#ADR_ROOTS[@]} -gt 0 ]; then
  ADR_GIT_SHA=$(git log -1 --format=%H -- "${ADR_ROOTS[@]}" 2>/dev/null | cut -c1-12)
  [ -n "$ADR_GIT_SHA" ] && WT_HASH=$(echo "${WT_HASH} ${ADR_GIT_SHA}" | shasum | cut -c1-12)
fi

CACHE_KEY="${HEAD_SHA}_${BASE_SHA}_${WT_HASH}_v5"
STATE_DIR="$HOME/.claude/gate-state/$REPO_SLUG"
STATE_FILE="$STATE_DIR/${BRANCH_SAFE}.json"
CONTEXT_CACHE_FILE="$STATE_DIR/${BRANCH_SAFE}.context.json"
# Dismissal registry — false-positive suppression, kept OUTSIDE CACHE_KEY so a
# rejected finding stays suppressed across diff churn. See references/dismissals.md.
DISMISS_FILE="$STATE_DIR/${BRANCH_SAFE}.dismissed.json"
mkdir -p "$STATE_DIR"
[ -f "$DISMISS_FILE" ] || echo '{"version":1,"dismissals":[]}' > "$DISMISS_FILE"
```

### 1c. Findings cache lookup

If `FORCE_FRESH=0`:

1. Read `$STATE_FILE`.
2. If `cache_key == CACHE_KEY` AND `cached_at` is within 7 days, **cache hit**: skip the subagent run, but **still run the Step 4 render core** over the cached `findings[] + dismissed[]` — the dismissal registry is independent of `CACHE_KEY`, so a dismissal added since the cached run (e.g. via `--dismiss`, or a newly-resolved thread on a prior full run) must apply. Re-partition, recompute IDs, render, then exit.
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
- **ADR** (if stale): walk `ADR_ROOTS`, determine applicability via frontmatter `paths:` glob, filename keyword match, or body mention. See `references/context-sources.md` § F3.
- **CLAUDE.md** (if stale): emit each `$CLAUDE_MD_LIST` file verbatim under a `### <path>` heading. See `references/context-sources.md` § F2.
- **devsql** (if stale): per changed file, last 10 history/jhistory rows. Cap at 80 total.

Merge fetched + cached portions into `$TMP_DIR/context-bundle.md` with the section headers from `references/context-sources.md`. Write the new freshness signals to `$TMP_DIR/freshness-signals.json`.

## Step 2: Get diff, detect stack, scope-gate

### 2a. Diff

```bash
git diff $BASE_SHA...HEAD --name-only > "$TMP_DIR/diff-summary.txt"
git diff $BASE_SHA...HEAD              > "$TMP_DIR/diff-full.txt"

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

Each reviewer is handed the diff scoped to its concern: the JSX reviewers (`react`, `a11y`, `i18n`) read `diff-tsx*`; every other reviewer reads `diff-code*`; the context-checker's CLAUDE.md/ADR synthesis reads `diff-full.txt`.

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

Full spec: `references/scope-gate.md`. Hard-stops here `exit 0` directly — they do NOT spawn reviewers.

**File-count hard-stop** (>200 files): emit the banner from `references/scope-gate.md`, exit unless `--ignore-scope-gate` (in which case, set `FILE_COUNT_BANNER` and continue).

**Suspicious-files classifier**:

- Skip if `FILE_COUNT <= 1`.
- Determine intent (Linear title/body → PR title/body → last commit → branch name).
- Run the Haiku classifier (single subagent call, read-only, model: haiku) — cache its result at `$STATE_DIR/${BRANCH_SAFE}.scope.json` keyed on SHA-12 of `CHANGED_FILES`.
- Decision: 0 SUSPICIOUS → silent. 1–3 → `SUSPICIOUS_BANNER` (soft-warn). ≥4 → hard-stop unless `--ignore-scope-gate`.

## Step 3: Run the gate — parallel reviewer subagents

The orchestration is a fixed three-stage pipeline: **parallel reviewers → tier-scaled adversarial verify → context annotation**, with CLAUDE.md/ADR synthesis running alongside the reviewers. You drive it directly with your harness's subagent primitive — spawn concurrently where the harness allows (Claude Code: multiple `Agent`/`Task` calls in one message; Codex: its subagent spawn), collect results, spawn the next stage.

Every subagent is **read-only** and writes its JSON result to a file in `$TMP_DIR` — files are the source of truth (not the return message), so collection is robust across harnesses. The finding shape, rule enums, tier rules, and Boy-Scout constraints all live in the `agents/*.md` system prompts; the prompts below only supply run-scoped paths and the stage's task.

### 3a. Prepare the reviewer list

```bash
# simplify-reviewer covers slop too (loads /simplify + /ai-skills:code-slop).
REVIEWERS=(
  "bug-reviewer"
  "solid-reviewer"
  "security-reviewer"
  "simplify-reviewer"
)
[ $SPAWN_REACT -eq 1 ]     && REVIEWERS+=("react-reviewer")
[ $SPAWN_A11Y -eq 1 ]      && REVIEWERS+=("a11y-reviewer")
[ $SPAWN_I18N -eq 1 ]      && REVIEWERS+=("i18n-reviewer")
[ $SPAWN_MIGRATION -eq 1 ] && REVIEWERS+=("migration-reviewer")
```

The subagent type is the reviewer name prefixed for your harness's plugin namespace (Claude Code: `ai-skills:bug-reviewer`). The JSX reviewers (`react`, `a11y`, `i18n`) read `diff-tsx`; all others read `diff-code`.

### 3b. Stage 1 — reviewers + synthesis (parallel)

In **one** batch, spawn every reviewer in `REVIEWERS` plus the context-checker in synthesize mode. Each reviewer prompt:

```
Review this branch's diff. You are <reviewer>.

Artifacts (scoped to your concern — files outside it are intentionally omitted as noise):
- Diff: <TMP_DIR>/<diff-code|diff-tsx>.txt
- Plus-lines (+ lines per file): <TMP_DIR>/<diff-code|diff-tsx>-plus.txt
- Context bundle (CLAUDE.md + ADRs + Linear + PR + sessions): <TMP_DIR>/context-bundle.md

Read whatever else you need — full versions of changed files, imported modules, schemas,
callers — to reason. The diff scopes WHERE a finding is anchored, NOT what you may read. A
defect whose trigger is on a + line but whose evidence lives in a non-diff file IS in scope:
anchor it to the diff line, cite the external file in evidence.

Constraints:
- Boy Scout asymmetry: adjacent (non-+, legacy) code may be flagged MAJOR/NIT but never BLOCKER.
- Read-scope ≠ finding-scope: read any file to reason; only REPORT findings anchored to changed lines.
- Read-only. No edits, no shell mutations.

Write your findings as JSON matching your output schema to <TMP_DIR>/findings-<reviewer>.json
— the object { "findings": [...] }, nothing else in the file. Empty findings is valid — most
diffs have few or none.
```

Context-checker synthesize prompt (subagent type `context-checker`):

```
MODE: synthesize

Read:
- Diff: <TMP_DIR>/diff-full.txt
- Context bundle: <TMP_DIR>/context-bundle.md

Walk the diff against the bundle's ## CLAUDE.md and ## ADR sections. Emit synthesized findings
for documented-rule violations (claude-md-violation / adr-violation) per your instructions.
There are no input findings yet — do NOT annotate. Write { "annotations": [], "synthesized": [...] }
to <TMP_DIR>/context-synth.json.
```

If a reviewer's output file is missing or invalid JSON, re-spawn that reviewer **once**; if it fails again, treat its findings as empty and continue.

### 3c. Collect + dedup

Read every `$TMP_DIR/findings-<reviewer>.json`. Concatenate their `findings[]`. Dedup per `(file, line)`: walk reviewers in `REVIEWERS` order; the first reviewer to claim a `(file:line)` **owns** it (tag the finding with its `reviewer`), later duplicates merge into the owner as `also_flagged_by: [{reviewer, rule_id}]` and are dropped — a duplicate never spawns its own skeptics.

### 3d. Stage 2 — tier-scaled adversarial verify

For each owned finding, spawn skeptics scaled by tier — **BLOCKER → 3, MAJOR → 1, NIT → 0**. Spawn all skeptics for all findings in **one** batch (they are independent). Each skeptic (subagent type `skeptic`) gets:

```
You are an adversarial skeptic (independent instance <i>). A <reviewer> flagged this finding<
 on PR #<n> — if a PR>. Try hard to REFUTE it. Default to refuted=true when uncertain —
refuted=false ONLY if it is clearly a real defect after investigation.

FINDING:
- rule_id: <rule_id>
- file: <file>  line: <line>  (location: <location>)
- tier: <tier>
- message: <message>
- evidence: <evidence>
- suggested_fix: <suggested_fix>

Read the cited region (±40 lines) and every other file the finding cites. Budget ≤6 tool calls.
Write { "refuted": <bool>, "reason": "<one sentence>" } to <TMP_DIR>/skeptic-<rule_id>-<line>-<i>.json.
```

Collect each finding's skeptic verdicts into `verifications[]`. **Drop** the finding when refuters reach the threshold: BLOCKER survives iff `<2 of 3` refute; MAJOR survives iff `0 of 1` refute. NIT runs 0 skeptics — it is shown, `verifications: []`, never adversarially checked (NITs never affect the verdict, so verifying them is pure cost).

### 3e. Stage 3 — context annotation

Once the survivors are known, spawn the context-checker **once** in annotate mode (subagent type `context-checker`) over the survivor set:

```
MODE: annotate

Context bundle: <TMP_DIR>/context-bundle.md

Annotate each of these <N> surviving findings with a verdict (OK/CONFLICT/UNCERTAIN/DISMISSED)
per your instructions. Do NOT synthesize new findings (synthesis already ran). Write
{ "annotations": [...], "synthesized": [] } to <TMP_DIR>/context-annotate.json.

FINDINGS:
<JSON: [{file, line, rule_id, tier, message}, ...] for each survivor>
```

Skip this call if there are no survivors.

### 3f. Merge

- Merge `context-annotate.json` annotations onto survivors by `(file, line, rule_id)`: copy `verdict → context_verdict`, `source → context_source`, `citation → context_citation`, `reason → context_reason`, and `dismiss_confidence` when present.
- Read `context-synth.json`; each synthesized finding gets `reviewer: "context-checker"`, `verifications: []`, and joins the finding set (it skips verify — a documented-rule violation is not a judgment call).

The finding set flowing into Step 4 is `[...survivors, ...synthesized]`.

### 3g. Failure modes

- **Subagent type not found**: verify Step 0 passed and the plugin is loaded (the `agents/*.md` ship at the plugin root).
- **A reviewer errors terminally**: treat its findings as empty (Step 3b retry already tried once) and continue — a missing reviewer degrades coverage, it does not abort the gate.

## Step 4: Compute verdict

### 4a. Banners

Emit any non-empty banner verbatim, in this order:

- `WRONG_BASE_BANNER`
- `FILE_COUNT_BANNER` (only when `--ignore-scope-gate` bypassed a >200 hard-stop)
- `SUSPICIOUS_BANNER` (soft-warn or bypassed hard-stop)

If none fired, skip this sub-step.

### 4a-bis. Apply the dismissal registry (partition active vs dismissed)

Before counting, partition the finding set into **active** and **dismissed** using the dismissal registry. This is the shared render core — it runs on every output path (fresh run, cache-hit replay, manual flag). On a fresh run, first **upsert** any context-checker `DISMISSED` annotations into the registry. Full spec — anchor computation, upsert, and `--dismiss/--undismiss/--show-dismissed` handling — in `references/dismissals.md`.

In short: for each finding compute its content-anchor `gate_anchor "$rule_id" "$file" "$line"`; if the anchor is in `$DISMISS_FILE` → **dismissed**, else → **active**. Only **active** findings flow into verdict math and the `B/M/N` lists; dismissed ones get `D1, D2, …` and a separate section.

### 4b. Verdict math

Count **active** findings by tier (dismissed findings never count):

| Verdict             | Condition                  |
| ------------------- | -------------------------- |
| **PASS**            | 0 BLOCKER, 0 MAJOR, 0 NIT  |
| **PASS WITH NOTES** | 0 BLOCKER, ≥1 MAJOR or NIT |
| **FAIL**            | ≥1 BLOCKER                 |

### 4c. Assign stable IDs

Sort findings by tier (BLOCKER → MAJOR → NIT), then by reviewer, then by `(file, line)`. Within each tier walk in order:

- BLOCKERs → `B1, B2, ...`
- MAJORs → `M1, M2, ...`
- NITs → `N1, N2, ...`

Persist IDs on each finding so a cache-hit re-render is byte-stable.

### 4d. Render

```
### Gate Verdict: <PASS | PASS WITH NOTES | FAIL>

Diff: <N> files, +<add>/-<del>

BLOCKER: <N>
MAJOR:   <N>
NIT:     <N>
```

For PASS / PASS WITH NOTES:

```
→ This PR meets the merge bar. MAJOR and NIT items are informational only.
```

For FAIL:

```
→ This PR cannot merge until BLOCKER items are resolved.
```

Then list findings grouped by tier, then by reviewer:

```
## BLOCKER

### B1 — [security-reviewer] security-sql-injection
- `src/db/users.ts:42` (diff-line) [refute votes: 0/3]
  message: User input concatenated into raw SQL query
  evidence: `db.query("SELECT * FROM users WHERE id = " + req.params.id)`
  fix: Use parameterized query: `db.query("SELECT * FROM users WHERE id = $1", [req.params.id])`

## MAJOR

### M1 — [solid-reviewer] solid-srp
- `src/services/booking.ts:120` (diff-line) [refute votes: 0/1] ❔ ambiguous historical context
  message: BookingService now handles 4 unrelated responsibilities
  evidence: …
  fix: Extract pricing logic into PricingCalculator
  context: Linear NAB-204 mentions "BookingService is the gateway, by design"
```

Display `[refute votes: K/N]` where N = `verifications.length` and K is the count of skeptics who refuted. Verify is tier-scaled: BLOCKER runs 3 skeptics (`K/3`, survives iff K < 2), MAJOR runs 1 (`K/1`, survives iff K = 0), NIT runs 0 — render `[unverified]` instead of a vote count (NITs never affect the verdict, so they are shown but not adversarially checked). A deduped duplicate (`also_flagged_by` present) appends `(also: <reviewer>)`.

For `context_verdict`:

- `OK` → no badge
- `UNCERTAIN` → `❔ ambiguous historical context` + cite `context_citation`
- `CONFLICT` → `⚠️ conflicts with past decision` + cite `context_citation`

For synthesized `claude-md-violation` / `adr-violation`, render the citation as the `rule reference:` line.

After the active findings, render the `Dismissed` section (omit if there are no dismissed findings). Full format in `references/dismissals.md`:

```
## Dismissed (suppressed — not counted toward the verdict)

### D1 — [security-reviewer] security-sql-injection
- `src/db/users.ts:42` · resolved · PR thread by @author
  was: User input concatenated into raw SQL query
  citation: "id is validated upstream — see middleware/auth.ts:30"
```

Render `· resolved` for `confidence: resolved`/`manual`, and `· rebutted (thread still open)` for `rebutted`.

After the last finding (active or dismissed), append:

```
Tip: reference findings by ID to target follow-up fixes — e.g. "fix B1, M1 and N1".
Tip: reviewing someone else's PR? Invoke the `pr-comment` skill to post these findings as a review (drafted via humanizer).
Tip: a dismissed finding reappears automatically if its code is edited (the dismissal is keyed on the code, not the line).
Tip: --dismiss <ids> to suppress a false-positive; --undismiss <Dn> to bring one back; --show-dismissed to list them.
```

## Step 5: Persist state

### 5a. Findings cache

Write `$STATE_FILE`:

```json
{
  "cache_key": "<CACHE_KEY>",
  "cached_at": "<ISO timestamp>",
  "verdict": "PASS | PASS WITH NOTES | FAIL",
  "findings": [ { "id": "B1", ... }, ... ],
  "dismissed": [ { "id": "D1", "anchor": "<sha>", "source": "pr-thread|manual", "confidence": "resolved|rebutted|manual", "citation": "...", ... full finding payload ... }, ... ]
}
```

`dismissed[]` carries each suppressed finding's full payload plus its `anchor`/`source`/`confidence`/`citation`, so `--undismiss` can promote it back and a cache-hit replay can re-partition without re-running the gate. The registry itself (`$DISMISS_FILE`) is the source of truth for *what* is dismissed; `dismissed[]` is the last-rendered snapshot.

### 5b. Context bundle cache

Write `$CONTEXT_CACHE_FILE`:

```json
{
  "key": "<BRANCH_SAFE>_v5",
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
find /tmp -maxdepth 1 -type d -name 'gate-*' -mmin +1440 -print 2>/dev/null \
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
  git show-ref --verify --quiet "refs/heads/$(echo "$b" | tr '_' '/')" || rm -f "$f"
done
```

## Execution notes

- **Portable orchestration**: reviewers and skeptics are spawned directly via the harness subagent primitive (Claude Code `Agent`/`Task`, Codex subagents) — no Workflow tool, no agent teams. Runs unchanged on any harness that can spawn a read-only subagent and read a file.
- **Pipeline shape**: parallel reviewers → per-finding tier-scaled verify → single context annotation. CLAUDE.md/ADR synthesis (`context-checker` in `MODE: synthesize`) runs alongside the reviewers; the annotation pass (`MODE: annotate`) runs once at the end over survivors.
- **Tier-scaled verify**: BLOCKER → 3 independent skeptics (drop if ≥2 refute), MAJOR → 1 skeptic (drop if it refutes), NIT → 0 (shown, unverified). Skeptics are refute-prompted (default refuted=true if uncertain) with a ≤6 tool-call budget. This replaces the legacy self-consistency vote + validator with a single adversarial pass.
- **Dedup**: findings are claimed per `(file,line)`; the first reviewer to claim a line owns it, later duplicates merge in as `also_flagged_by` without spawning their own skeptics.
- **Parallelism**: spawn each stage's subagents in one batch so the harness can run them concurrently; degrades gracefully to sequential where it cannot.
- **Boy Scout asymmetry**: adjacent legacy code can be flagged (MAJOR/NIT) but never blocks the gate.
- **Tier semantics**: only BLOCKER affects the verdict. MAJOR and NIT are informational.
- **Dismissals**: false-positives are suppressed via a per-branch registry kept *outside* `CACHE_KEY` (`references/dismissals.md`). Suppression is keyed on the offending code's text (a content-anchor), so it survives diff churn but lifts the moment the code is edited. Two populators: PR review threads the author resolved (auto, via the context-checker) and `--dismiss <ids>` (manual). Dismissed findings are excluded from `findings[]` — so `pr-comment` never re-posts them — and from the verdict, but always shown in a `Dismissed (N)` section.
- **Read-only**: the gate never modifies code. Every subagent is read-only; the skill returns a verdict only.
- **Reviewer logic is single-source**: the finding shape, rule enums, tier rules, and per-reviewer heuristics live in the shared `agents/*.md` (also used by `gate-wf`). This skill supplies only run-scoped paths and the stage's task.

## References

- `references/context-sources.md` — CLAUDE.md (F2) + ADR (F3) discovery and enforcement
- `references/scope-gate.md` — file-count + suspicious-files classifier (Step 2c)
- `references/dismissals.md` — dismissal registry: content-anchor identity, PR-thread + manual populators, render core, `--dismiss`/`--undismiss`/`--show-dismissed`
