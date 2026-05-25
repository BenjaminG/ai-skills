# Scope-gate (Step 2c)

> **Status**: scope-gate runs in `Step 2c` of `SKILL.md` — between diff/stack detection (Step 2a/2b) and parallel review (Step 3). Hard-stops here exit before any Opus reviewer spawns and **do NOT increment the cycle counter**.

This file specifies three deterministic-or-cheap-LLM checks that gate the rest of the pipeline. They share a single Haiku call (when needed) so the cost is ≤ 1 cheap call, not three.

---

## Why scope-gate exists

The gate's most expensive operation is Step 3 (5–8 Opus reviewers × 3 passes each = 15–24 Opus passes). Wasting that budget on a botched merge-base, a runaway rebase, or a PR whose changed files have nothing to do with the stated intent is the single biggest cost trap. The scope-gate catches those cases up-front and **refuses to proceed** rather than burn cost on noise.

Scope-gate is also where unobvious upstream mistakes surface in the report: wrong base branch, accidental scope creep.

---

## F10 — wrong-base-warning (deterministic)

**Trigger**: always.

**Logic**:

```bash
# Compute auto-detected default
AUTO_DETECTED=$(git rev-parse --verify main >/dev/null 2>&1 && echo main \
  || (git rev-parse --verify master >/dev/null 2>&1 && echo master || echo develop))

# Skip warn if BASE_ARG was explicit AND matches a standard name
if [ -n "$BASE_ARG" ]; then
  case "$BASE_ARG" in
    main|master|develop) WRONG_BASE_WARN=0 ;;
    *) WRONG_BASE_WARN=1 ;;
  esac
else
  # Auto-detect path: warn if we fell through main → not main
  case "$AUTO_DETECTED" in
    main) WRONG_BASE_WARN=0 ;;
    *)    WRONG_BASE_WARN=1 ;;
  esac
fi
```

**Output**: top-of-report banner appended to Step 7 output. Format:

```
⚠️  Base: <BASE> (<reason>)
   <hint to verify intent>
```

Examples:

- BASE_ARG explicit non-standard: `Base: release/2026-q2 (non-standard — verify this is intentional, otherwise pass main|master|develop explicitly)`
- Auto-detect fell to develop: `Base: develop (auto-detected — main not found locally; verify your branch is rebased on the right base)`

**Cycle / verdict impact**: **NONE** — banner is informational only, never blocks, never alters PASS/FAIL.

**Cost**: free.

---

## F1 — file-count hard-stop (deterministic)

**Trigger**: always, after Step 2 (diff already computed).

**Logic**:

```bash
FILE_COUNT=$(echo "$CHANGED_FILES" | wc -l)
if [ "$FILE_COUNT" -gt 200 ]; then
  HARD_STOP=1
fi
```

**Output** (when fired):

```
🛑 SCOPE-GATE — TOO MANY FILES

  This diff touches <FILE_COUNT> files vs the base.
  That is almost always a botched rebase or merge — gate refuses to review it.

  Try:
    • git status                         # check for unintended changes
    • git diff <BASE> --stat | head -50   # inspect the largest files
    • git rebase --abort                  # if mid-rebase

  If this is intentional (mass codemod, generated code), bypass with:
    /gate <BASE> --ignore-scope-gate
```

**Action**: skill exits cleanly with no verdict written. **Cycle counter is preserved** (Step 10a writes `cycle: state.cycle` unchanged, not `state.cycle + 1`).

**Cost**: free.

---

## F9 — suspicious-files-warning (LLM-classified)

**Trigger**: `FILE_COUNT > 1` (single-file diffs are trivially in-scope).

**Cost**: 1 Haiku call. The result is cached with the context bundle (`bundle_sources.scope_classification`) and re-runs only when `CHANGED_FILES` changes (so a re-run with the same tree skips the call).

### Intent source — fallback chain

The classifier needs an "intent statement" to judge each file against. Gate has no PR title of its own, so we walk this chain and use the **first available source**:

1. **Linear ticket title + body** — already in the context bundle (Step 1f freshness probe). Free if cached.
2. **GitHub PR title + body** — `gh pr view --json title,body` for the current branch (only if `gh` is available and a PR exists).
3. **Last commit message subject + body** — `git log -1 --format=%s%n%n%b HEAD`.
4. **Branch name** — `git rev-parse --abbrev-ref HEAD`, with separators (`-`, `_`, `/`) normalized to spaces, prefixes stripped (`feat/`, `fix/`, `chore/`, `<TICKET>-`).

The chain is tried in order, the first non-empty result is the intent. Capture which source was used in the cached classification (`intent_source: linear|pr|commit|branch`) — surfaces in the banner for transparency.

### Classification (Haiku call)

Prompt the classifier with:

- Intent statement (from chain above)
- The list of changed files (paths only, no diff content)
- Required output: a JSON array `[{file, classification, reason}]` where `classification ∈ {IN_SCOPE, PLAUSIBLY_IN_SCOPE, SUSPICIOUS}`

Cache the result alongside the context bundle so repeat runs reuse it.

### Decision rules (deterministic, applied to the classifier output)

```
SUSPICIOUS_COUNT = count of files where classification == "SUSPICIOUS"

| SUSPICIOUS_COUNT | Action                                                |
|------------------|-------------------------------------------------------|
| 0                | Silent pass — no banner                               |
| 1–3              | Soft-warn banner; Step 3 still runs                   |
| ≥ 4              | Hard-stop — exit clean (Step 3 does NOT run)          |
```

### Soft-warn banner format (1–3 SUSPICIOUS)

```
⚠️  SCOPE-GATE — files possibly out-of-scope (intent source: <source>)

  Intent: "<intent statement first 100 chars>"

  Suspicious files:
    • path/foo.ts — <reason>
    • path/bar.ts — <reason>

  Continuing review. Bypass this banner with --ignore-scope-gate.
```

The banner appears **above** the verdict in Step 7. PASS/FAIL math is unchanged.

### Hard-stop banner format (≥ 4 SUSPICIOUS)

```
🛑 SCOPE-GATE — too many files out-of-scope (intent source: <source>)

  Intent: "<intent statement first 100 chars>"

  Suspicious files (<N>):
    • path/foo.ts — <reason>
    ...

  This is almost always: scope creep, a stale rebase, or a wrong branch.
  Either narrow the diff (split the PR) or bypass with --ignore-scope-gate
  if you are sure.
```

**Action**: skill exits cleanly with no verdict written. **Cycle counter is preserved** (same as F1).

---

## Bypass flag — `--ignore-scope-gate`

When the user passes `--ignore-scope-gate`:

- `FILE_COUNT > 200` warns once at the top of the report but does NOT exit
- `SUSPICIOUS_COUNT > 4` warns once at the top of the report but does NOT exit
- Soft-warn (1–3) still surfaces; bypass doesn't suppress informational banners

The flag is intentional: gate trusts the user once they've explicitly said "I know the scope is wide on purpose."

---

## Implementation order

1. F10 (wrong-base) is purely deterministic — implement first as it requires no LLM call and no caching.
2. F1 (file-count) is deterministic — implement second, before any classifier call.
3. F9 (suspicious-files) calls the classifier only if F1 didn't already hard-stop. Cache the result with the context bundle.

---

## Cycle / verdict impact summary

| Outcome | Cycle increment | Verdict written | Step 3 runs |
|---|---|---|---|
| F10 banner | yes (normal flow) | yes | yes |
| F1 hard-stop | **NO** | NO | NO |
| F9 hard-stop | **NO** | NO | NO |
| F9 soft-warn | yes (normal flow) | yes | yes |
| `--ignore-scope-gate` bypass | yes (normal flow) | yes | yes |
