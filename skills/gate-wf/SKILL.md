---
name: gate-wf
description: Workflow-native quality gate for branch changes — parallel reviewers (Bug, SOLID, Security, Simplify, Slop, optionally React/a11y/i18n/migration) with adversarial verify, CLAUDE.md/ADR enforcement, and a stable PASS / PASS WITH NOTES / FAIL verdict. Read-only. Built on Claude Code Workflows.
argument-hint: "[base-branch] [--force-fresh] [--ignore-scope-gate] [--resume <runId>]"
---

# Gate-WF — Workflow-native quality gate

!IMPORTANT: Follow this process exactly. Do not skip steps.

This skill is a **gate**, not a fixer. It returns a verdict; it does not modify code.

**Skill version**: `2`. Cache entries are keyed on this — bumping invalidates all caches at once.

## Prerequisites

- Workflows feature enabled: `CLAUDE_CODE_WORKFLOWS=1` in `settings.json` env.
- Plugin installed (this skill ships with `agents/*.md` and `workflows/gate.js` at the plugin root).

## Arguments

- `$0` (optional): base branch to diff against. If omitted, auto-detect (`main` → `master` → `develop`).
- `--force-fresh` (flag): bypass cache and re-fetch context bundle.
- `--ignore-scope-gate` (flag): downgrade Step 2 hard-stops (file-count, suspicious-files) to top-of-report banners. Soft-warn (1–3 SUSPICIOUS) is unaffected.
- `--resume <runId>`: resume a previous workflow run by ID (`wf_...`). Useful after editing `workflows/gate.js` or any `agents/*.md` to re-run only changed agent calls.

## Step 0: Verify reviewer skill dependencies

Reviewer agents invoke skills via slash-command. A skill is reachable when found in either the global skills dir (`~/.claude/skills/<name>/SKILL.md`) or any plugin cache (`~/.claude/plugins/cache/**/skills/<name>/SKILL.md`). `code-slop` ships with this plugin; the others are external and must be installed globally.

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
RESUME_ID=""

# Walk tokens. --resume takes the next token as its value.
SKIP_NEXT=0
TOKENS=()
for tok in $ARGS; do TOKENS+=("$tok"); done
for i in "${!TOKENS[@]}"; do
  if [ "$SKIP_NEXT" -eq 1 ]; then SKIP_NEXT=0; continue; fi
  tok="${TOKENS[$i]}"
  case "$tok" in
    --force-fresh)       FORCE_FRESH=1 ;;
    --ignore-scope-gate) IGNORE_SCOPE_GATE=1 ;;
    --resume)
      RESUME_ID="${TOKENS[$((i+1))]:-}"
      [ -z "$RESUME_ID" ] && { echo "--resume requires a runId" >&2; exit 2; }
      SKIP_NEXT=1
      ;;
    --*) echo "unknown flag: $tok" >&2; exit 2 ;;
    *)
      [ -z "$BASE_ARG" ] && BASE_ARG="$tok" || { echo "extra positional: $tok" >&2; exit 2; }
      ;;
  esac
done
```

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

CACHE_KEY="${HEAD_SHA}_${BASE_SHA}_${WT_HASH}_v2"
STATE_DIR="$HOME/.claude/gate-wf-state/$REPO_SLUG"
STATE_FILE="$STATE_DIR/${BRANCH_SAFE}.json"
CONTEXT_CACHE_FILE="$STATE_DIR/${BRANCH_SAFE}.context.json"
mkdir -p "$STATE_DIR"
```

### 1c. Findings cache lookup

If `FORCE_FRESH=0` and `RESUME_ID=""`:

1. Read `$STATE_FILE`.
2. If `cache_key == CACHE_KEY` AND `cached_at` is within 7 days, **cache hit**: print the cached verdict and findings verbatim, then exit. The cached findings carry their original `B1`/`M1`/`N1` IDs so the user can reference them.
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
- **GitHub PR** (if stale): `gh pr view --json number,title,body,comments,reviews,updatedAt`.
- **ADR** (if stale): walk `ADR_ROOTS`, determine applicability via frontmatter `paths:` glob, filename keyword match, or body mention. See `references/context-sources.md` § F3.
- **CLAUDE.md** (if stale): emit each `$CLAUDE_MD_LIST` file verbatim under a `### <path>` heading. See `references/context-sources.md` § F2.
- **devsql** (if stale): per changed file, last 10 history/jhistory rows. Cap at 80 total.

Merge fetched + cached portions into `$TMP_DIR/context-bundle.md` with the section headers from `references/context-sources.md`. Write the new freshness signals to `$TMP_DIR/freshness-signals.json`.

## Step 2: Get diff, detect stack, scope-gate

### 2a. Diff

```bash
git diff $BASE_SHA...HEAD --name-only > "$TMP_DIR/diff-summary.txt"
git diff $BASE_SHA...HEAD              > "$TMP_DIR/diff-full.txt"

# `+` lines per file (input to reviewers)
git diff $BASE_SHA...HEAD | awk '
  /^diff --git/ { f=$3; sub(/^a\//,"",f) }
  /^\+\+\+/ { f=substr($2,3) }
  /^\+/ && !/^\+\+\+/ { print f": "substr($0,2) }
' > "$TMP_DIR/plus-lines.txt"
```

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

## Step 3: Run the gate as a dynamic workflow

The skill writes a prompt that describes the orchestration. Claude generates and runs
the workflow script, then returns `{ findings: [...] }`.

### 3a. Prepare flag-conditional reviewer list

```bash
REVIEWERS=(
  "ai-skills:bug-reviewer"
  "ai-skills:solid-reviewer"
  "ai-skills:security-reviewer"
  "ai-skills:simplify-reviewer"
  "ai-skills:slop-reviewer"
)
[ $SPAWN_REACT -eq 1 ]     && REVIEWERS+=("ai-skills:react-reviewer")
[ $SPAWN_A11Y -eq 1 ]      && REVIEWERS+=("ai-skills:a11y-reviewer")
[ $SPAWN_I18N -eq 1 ]      && REVIEWERS+=("ai-skills:i18n-reviewer")
[ $SPAWN_MIGRATION -eq 1 ] && REVIEWERS+=("ai-skills:migration-reviewer")

REVIEWERS_LIST=$(printf '  - %s\n' "${REVIEWERS[@]}")
```

### 3b. Build the orchestration prompt

The prompt is the contract. It tells Claude exactly what workflow shape to generate.

```
ultracode: Run a deterministic quality gate on this branch's diff.

ARTIFACTS (read these files inside the workflow):
- Diff: $TMP_DIR/diff-full.txt
- Plus-lines (filtered to + lines per file): $TMP_DIR/plus-lines.txt
- Context bundle (CLAUDE.md + ADRs + Linear + PR + past sessions): $TMP_DIR/context-bundle.md
- Spawn flags: react=$SPAWN_REACT, a11y=$SPAWN_A11Y, i18n=$SPAWN_I18N, migration=$SPAWN_MIGRATION
- Session ID: $SESSION_ID

ORCHESTRATION SHAPE (your generated workflow must follow this exactly):

Phase 1 — Parallel Review:
  Spawn these reviewer agents in parallel, each with the schema below:
$REVIEWERS_LIST
  Each reviewer reads diff-full.txt + plus-lines.txt and returns findings.

  Per-finding schema:
  {
    rule_id: string,           // stable identifier, e.g. "security-sql-injection"
    file: string,
    line: number,
    location: "diff-line" | "adjacent",  // adjacent = legacy code touched but not changed
    tier: "BLOCKER" | "MAJOR" | "NIT",
    message: string,
    evidence: string,          // 1-3 lines from the file showing the issue
    suggested_fix: string
  }

Phase 2 — Adversarial Verify (per-finding, streaming):
  As each reviewer returns, for every finding it surfaced, spawn 3 independent
  skeptic agents (agentType: ai-skills:skeptic-reviewer) that try to refute it.
  Each skeptic reads the finding + the relevant file region.
  Skeptic schema: { refuted: boolean, reason: string }
  Drop findings where ≥2 of 3 skeptics return refuted=true.
  Survivors carry `verifications: [{refuted, reason}, ...]` (length 3).

Phase 3 — Context Check (single agent):
  Spawn ai-skills:context-checker once with: surviving findings + context bundle.
  It annotates each finding with:
    - context_verdict: "OK" | "CONFLICT" | "UNCERTAIN"
    - context_source:  "linear" | "pr" | "session" | "claude-md" | "adr" | "none"
    - context_citation: string (when not OK)
    - context_reason: string (when not OK)
  It may also SYNTHESIZE new findings for CLAUDE.md or ADR violations not
  already surfaced by reviewers. Synthesized findings carry:
    - reviewer: "context-checker"
    - citation: string (claude-md path or ADR ID)
    - source: "claude-md" | "adr"
  Synthesized findings have empty verifications[] and skip Phase 2.

CONSTRAINTS:
- Boy Scout asymmetry: adjacent (legacy) code may be flagged MAJOR/NIT but never BLOCKER.
- Reviewers are READ-ONLY. No edits, no shell.
- Use pipeline() so per-finding verify can start as soon as each reviewer returns
  (don't wait for all reviewers to finish before starting verify).
- Workflow must return { findings: [...] } as a single JSON object.

Generate the workflow script and run it.
```

### 3c. Submit and capture result

The skill issues this prompt to Claude in the active session. Claude generates the
workflow script via the dynamic workflows runtime, executes it, and returns
`{ findings: [...] }`.

After the run completes, capture the `runId` from `/workflows` (shown in the task
panel). Pass it to Step 5 for caching and to the verdict footer.

### 3d. Failure modes

If Claude declines to generate a workflow (e.g., user has workflows disabled):
- Surface the error to the user and exit.
- If `disableWorkflows=true` in settings, the skill cannot proceed.

If a reviewer agent type is not found:
- The dynamic workflow will surface this as an error per agent.
- Verify Step 0 dependencies passed, and that the plugin is loaded.

## Step 4: Compute verdict

### 4a. Banners

Emit any non-empty banner verbatim, in this order:

- `WRONG_BASE_BANNER`
- `FILE_COUNT_BANNER` (only when `--ignore-scope-gate` bypassed a >200 hard-stop)
- `SUSPICIOUS_BANNER` (soft-warn or bypassed hard-stop)

If none fired, skip this sub-step.

### 4b. Verdict math

Count findings by tier:

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
### Gate-WF Verdict: <PASS | PASS WITH NOTES | FAIL>

Diff: <N> files, +<add>/-<del>
Run: <runId>

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
- `src/services/booking.ts:120` (diff-line) [refute votes: 1/3] ❔ ambiguous historical context
  message: BookingService now handles 4 unrelated responsibilities
  evidence: …
  fix: Extract pricing logic into PricingCalculator
  context: Linear NAB-204 mentions "BookingService is the gateway, by design"
```

Display `[refute votes: K/3]` where K is the count of skeptics who refuted (still surviving means K < 2).

For `context_verdict`:

- `OK` → no badge
- `UNCERTAIN` → `❔ ambiguous historical context` + cite `context_citation`
- `CONFLICT` → `⚠️ conflicts with past decision` + cite `context_citation`

For synthesized `claude-md-violation` / `adr-violation`, render the citation as the `rule reference:` line.

After the last finding, append:

```
Tip: reference findings by ID to target follow-up fixes — e.g. "fix B1, M1 and N1".
Tip: edit workflows/gate.js or any agents/*.md, then re-run with --resume <runId> to skip cached agent calls.
```

## Step 5: Persist state

### 5a. Findings cache

Write `$STATE_FILE`:

```json
{
  "cache_key": "<CACHE_KEY>",
  "cached_at": "<ISO timestamp>",
  "verdict": "PASS | PASS WITH NOTES | FAIL",
  "run_id": "<wf_...>",
  "findings": [ { "id": "B1", ... }, ... ]
}
```

### 5b. Context bundle cache

Write `$CONTEXT_CACHE_FILE`:

```json
{
  "key": "<BRANCH_SAFE>_v2",
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
```

## Execution notes

- **Requires**: `CLAUDE_CODE_WORKFLOWS=1` in `settings.json`.
- **Pipeline shape**: workflow uses `pipeline()` over reviewers — each reviewer's findings stream into per-finding adversarial verify the moment its review returns. No barrier between review and verify.
- **Adversarial verify**: 3 independent skeptics per finding, refute-prompted (default refuted=true if uncertain). Findings dropped if ≥2/3 refute.
- **Concurrency cap**: workflow runtime caps at 16 parallel agents per workflow. With 8 reviewers + 3 skeptics per finding, peak concurrency is queued automatically.
- **No `Date.now()` in the workflow**: all timestamps are stamped in this skill (bash + post-workflow). The workflow is purely deterministic for resume to work.
- **Resume**: `--resume <runId>` skips cached `(prompt, opts)` pairs. Edit `workflows/gate.js` or any `agents/*.md` to make targeted re-runs cheap.
- **Boy Scout asymmetry**: adjacent legacy code can be flagged (MAJOR/NIT) but never blocks the gate.
- **Tier semantics**: only BLOCKER affects the verdict. MAJOR and NIT are informational.
- **No auto-fix in v1**: v1 is read-only review. `--fix` mode is reserved for v2.
- **Coexists** with the legacy `gate` skill during migration.

## References

- `references/context-sources.md` — CLAUDE.md (F2) + ADR (F3) discovery and enforcement
- `references/scope-gate.md` — file-count + suspicious-files classifier (Step 2c)
