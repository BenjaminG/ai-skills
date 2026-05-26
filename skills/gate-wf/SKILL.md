---
name: gate-wf
description: Workflow-native quality gate for branch changes — parallel reviewers (SOLID, Security, Simplify, Slop, optionally React/a11y/i18n/migration) with adversarial verify, CLAUDE.md/ADR enforcement, and a stable PASS / PASS WITH NOTES / FAIL verdict. Read-only. Built on Claude Code Workflows.
argument-hint: "[base-branch] [--force-fresh] [--ignore-scope-gate] [--resume <runId>]"
---

# Gate-WF — Workflow-native quality gate

!IMPORTANT: Follow this process exactly. Do not skip steps.

This skill is a **gate**, not a fixer. It returns a verdict; it does not modify code.

**Skill version**: `1`. Cache entries are keyed on this — bumping invalidates all caches at once.

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

| Skill | Install |
|-------|---------|
| `vercel-react-best-practices` | `npx skills add https://github.com/vercel-labs/agent-skills --skill vercel-react-best-practices -g` |
| `solid` | `npx skills add https://github.com/ramziddin/solid-skills --skill solid -g` |
| `security-review` | `npx skills add https://github.com/getsentry/skills --skill security-review -g` |
| `code-slop` | Ships with this plugin. If missing, reinstall the `bgelis-ai-skills` plugin (`/plugin reinstall bgelis-ai-skills`). |
| `simplify` | `npx skills add https://github.com/brianlovin/claude-config --skill simplify -g` |

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

CACHE_KEY="${HEAD_SHA}_${BASE_SHA}_${WT_HASH}_v1"
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

| Cached vs Fresh | Action |
|---|---|
| equal | **reuse** cached portion |
| different | **re-fetch** |
| cached null, fresh not null | **fetch** |
| cached not null, fresh null | **re-fetch** (transient unavailability) |
| no cache file | **fetch all** |

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

## Step 3: Invoke the workflow

The workflow is registered by the plugin under the canonical name `ai-skills:gate` (auto-discovered from `<plugin-root>/workflows/gate.js`).

### 3a. Decide invocation shape based on payload size

Inline tool-call args have a hard size limit (~256 KB in practice). The diff alone can exceed this on real branches. Compute total args size first, then choose:

```bash
ARGS_BYTES=$(( $(wc -c < "$TMP_DIR/diff-full.txt") \
             + $(wc -c < "$TMP_DIR/diff-summary.txt") \
             + $(wc -c < "$TMP_DIR/plus-lines.txt") \
             + $(wc -c < "$TMP_DIR/context-bundle.md") ))
```

- **Small (`ARGS_BYTES` < 200000)**: invoke with `args` inline (3b).
- **Large (`ARGS_BYTES` ≥ 200000)**: write a bundled script and invoke with `scriptPath` (3c). `plusLines` is dropped from the bundle — reviewers see the full diff anyway.

### 3b. Inline invocation (small diffs)

```
Workflow({
  name: "ai-skills:gate",
  args: {
    diff: <contents of $TMP_DIR/diff-full.txt>,
    diffSummary: <contents of $TMP_DIR/diff-summary.txt>,
    plusLines: <contents of $TMP_DIR/plus-lines.txt>,
    contextBundle: <contents of $TMP_DIR/context-bundle.md>,
    spawnFlags: {
      react: SPAWN_REACT == 1,
      a11y: SPAWN_A11Y == 1,
      i18n: SPAWN_I18N == 1,
      migration: SPAWN_MIGRATION == 1,
    },
    sessionId: SESSION_ID,
  },
  resumeFromRunId: RESUME_ID || undefined,
})
```

### 3c. Bundled-script invocation (large diffs)

Build a script that hardcodes the args at the top, then concatenates the original `workflows/gate.js` body:

```bash
PLUGIN_ROOT=$(ls -d "$HOME/.claude/plugins/cache/"*/ai-skills/*/ 2>/dev/null | head -1)
GATE_JS="${PLUGIN_ROOT}workflows/gate.js"

node -e '
  const fs = require("fs");
  const args = {
    diff:          fs.readFileSync(process.env.DIFF, "utf8"),
    diffSummary:   fs.readFileSync(process.env.DIFFSUM, "utf8"),
    plusLines:     "",   // dropped intentionally; reviewers use diff
    contextBundle: fs.readFileSync(process.env.CTX, "utf8"),
    spawnFlags:    JSON.parse(process.env.FLAGS),
    sessionId:     process.env.SESSION,
  };
  const body = fs.readFileSync(process.env.GATE_JS, "utf8")
    .replace(/^export const meta\s*=\s*{[\s\S]*?};\s*/m, "");
  const meta = `export const meta = ${
    fs.readFileSync(process.env.GATE_JS, "utf8")
      .match(/export const meta\s*=\s*({[\s\S]*?});/)[1]
  };\n`;
  const argsLine = `const args = ${JSON.stringify(args)};\n`;
  fs.writeFileSync(process.env.OUT, meta + argsLine + body);
' \
  DIFF="$TMP_DIR/diff-full.txt" \
  DIFFSUM="$TMP_DIR/diff-summary.txt" \
  CTX="$TMP_DIR/context-bundle.md" \
  FLAGS="{\"react\":$( [ $SPAWN_REACT -eq 1 ] && echo true || echo false ),\"a11y\":$( [ $SPAWN_A11Y -eq 1 ] && echo true || echo false ),\"i18n\":$( [ $SPAWN_I18N -eq 1 ] && echo true || echo false ),\"migration\":$( [ $SPAWN_MIGRATION -eq 1 ] && echo true || echo false )}" \
  SESSION="$SESSION_ID" \
  GATE_JS="$GATE_JS" \
  OUT="$TMP_DIR/gate-bundled.js"
```

Then:

```
Workflow({
  scriptPath: "<TMP_DIR>/gate-bundled.js",
  resumeFromRunId: RESUME_ID || undefined,
})
```

The bundled script reuses the meta + body of the canonical workflow; only the `args` declaration is materialized. Resume keys still work because the bundled script is byte-stable across re-invocations of the same diff.

### 3d. Workflow resolution failures

If the workflow tool returns "workflow not found":
- Verify `CLAUDE_CODE_WORKFLOWS=1` is set in `settings.json`.
- Verify the plugin is loaded (`/plugin list` should show `bgelis-ai-skills`).
- For `claude --plugin-dir .` runs, verify `workflows/gate.js` exists at the plugin root.

The workflow returns `{ findings: [...] }`. Each finding carries:

- `rule_id, file, line, location, tier, message, evidence, suggested_fix` (from reviewer)
- `reviewer` (which reviewer surfaced it; `context-checker` for synthesized)
- `verifications: [{refuted, reason}, ...]` (3 skeptic verdicts; empty for synthesized)
- `context_verdict: OK | CONFLICT | UNCERTAIN`
- `context_source: linear | pr | session | claude-md | adr | none`
- `context_citation, context_reason` (when context_verdict is not OK)
- For synthesized findings only: `citation, source` (always claude-md or adr)

If the workflow tool returns an error, surface it to the user and exit. Do NOT retry automatically.

If `--resume` was used, the workflow's `runId` will match the requested ID. Otherwise, capture the new `runId` for the verdict footer.

## Step 4: Compute verdict

### 4a. Banners

Emit any non-empty banner verbatim, in this order:
- `WRONG_BASE_BANNER`
- `FILE_COUNT_BANNER` (only when `--ignore-scope-gate` bypassed a >200 hard-stop)
- `SUSPICIOUS_BANNER` (soft-warn or bypassed hard-stop)

If none fired, skip this sub-step.

### 4b. Verdict math

Count findings by tier:

| Verdict | Condition |
|---|---|
| **PASS** | 0 BLOCKER, 0 MAJOR, 0 NIT |
| **PASS WITH NOTES** | 0 BLOCKER, ≥1 MAJOR or NIT |
| **FAIL** | ≥1 BLOCKER |

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
  "key": "<BRANCH_SAFE>_v1",
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
