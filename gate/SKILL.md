---
name: gate
description: Deterministic quality gate for branch changes — runs parallel reviewers (React, SOLID, Security, Simplify, Slop) with self-consistency, returns a stable PASS / PASS WITH NOTES / FAIL verdict. Read-only by default; opt-in --fix applies BLOCKER fixes only.
argument-hint: "[base-branch] [--fix] [--force-fresh]"
---

# Gate

!IMPORTANT: Follow this process exactly. Do not skip steps.

This skill is a **gate**, not a fixer. It returns a verdict; it does not modify code unless `--fix` is passed.

**Skill version**: `1` — bump this number whenever the reviewer logic, rule enums, or pipeline changes. Cache entries are keyed on it, so bumping invalidates all caches at once.

## Arguments

- `$0` (optional): base branch to diff against. If omitted, auto-detect (`main` → `master` → `develop`).
- `--fix` (flag): apply BLOCKER findings that pass validator + context-checker. Never auto-commits.
- `--force-fresh` (flag): bypass cache and reset convergence counter for this branch.

## Step 0: Verify Dependencies

This skill invokes four external skills plus one Claude Code built-in. Before doing anything else, verify each is installed at `~/.claude/skills/<name>/SKILL.md`. `simplify` is a Claude Code built-in.

```bash
for s in vercel-react-best-practices applying-solid-principles security-review code-slop; do
  [ -f ~/.claude/skills/$s/SKILL.md ] && echo "OK  $s" || echo "MISS $s"
done
```

If any report `MISS`, stop and tell the user which skills are missing with the install command. Do not proceed until the user confirms they are installed.

| Skill | Install command |
|-------|-----------------|
| `vercel-react-best-practices` | `npx skills add https://github.com/vercel-labs/agent-skills --skill vercel-react-best-practices -g` |
| `applying-solid-principles` | `npx skills add https://github.com/BenjaminG/ai-skills --skill applying-solid-principles -g` |
| `security-review` | `npx skills add https://github.com/getsentry/skills --skill security-review -g` |
| `code-slop` | `npx skills add https://github.com/BenjaminG/ai-skills --skill code-slop -g` |
| `simplify` | Built-in to Claude Code — no install needed |

If the project does not use React/Next.js, `vercel-react-best-practices` is optional (the react-reviewer is skipped automatically).

**Soft dependencies for the context-fetcher.** Degrade gracefully if any are missing — log unavailable tools in the bundle and continue:

| Tool | Used for | Probe |
|------|----------|-------|
| `linear-cli` skill | Linear issue + comments | `[ -f ~/.claude/skills/linear-cli/SKILL.md ]` |
| `devsql` CLI | Past Claude Code sessions | `command -v devsql` |
| `gh` CLI | Open PR body + comments | `command -v gh && gh auth status` |

**Pre-supposed**: lint, typecheck, and tests have already run. The skill does NOT execute them. The user is responsible for ensuring the working tree is in a buildable state before invoking.

## Step 1: Resolve State, Cache, and Convergence

### 1a. Parse arguments

The skill receives a single argument string. Split it into a positional base branch and flags:

```bash
ARGS="$@"
BASE_ARG=""
FIX_FLAG=0
FORCE_FRESH=0

for tok in $ARGS; do
  case "$tok" in
    --fix)         FIX_FLAG=1 ;;
    --force-fresh) FORCE_FRESH=1 ;;
    --*)           echo "unknown flag: $tok" >&2; exit 2 ;;
    *)             [ -z "$BASE_ARG" ] && BASE_ARG="$tok" || { echo "extra positional: $tok" >&2; exit 2; } ;;
  esac
done
```

### 1b. Compute identifiers

```bash
# Repo slug for state path (short hash of repo root)
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_SLUG=$(echo -n "$REPO_ROOT" | shasum | cut -c1-12)

# Branch (sanitized for filesystem — slashes become underscores)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
BRANCH_SAFE=$(echo "$BRANCH" | tr '/' '_')

# Base branch (from arg or auto-detect)
BASE=${BASE_ARG:-$(git rev-parse --verify main >/dev/null 2>&1 && echo main || (git rev-parse --verify master >/dev/null 2>&1 && echo master || echo develop))}

# SHAs
HEAD_SHA=$(git rev-parse HEAD)
BASE_SHA=$(git merge-base $BASE HEAD)

# Working tree hash — captures unstaged + staged changes so the cache invalidates after --fix
# (HEAD doesn't change after --fix until the user commits, but the working tree does)
WT_HASH=$(git diff HEAD | shasum | cut -c1-12)

# Cache key — combines SHAs + working tree state + skill version
CACHE_KEY="${HEAD_SHA}_${BASE_SHA}_${WT_HASH}_v1"  # v1 = SKILL_VERSION from frontmatter

# State file path
STATE_DIR="$HOME/.claude/gate-state/$REPO_SLUG"
STATE_FILE="$STATE_DIR/${BRANCH_SAFE}.json"
mkdir -p "$STATE_DIR"
```

### 1c. Cleanup orphan states

List all `<STATE_DIR>/*.json` files. For each, derive the branch name by replacing `_` back to `/` (best-effort) and check existence with `git rev-parse --verify <branch>`. Delete state files for branches that no longer exist. Best-effort — failures here are non-fatal.

### 1d. Cache lookup

If `FORCE_FRESH` is 0:

1. Read `$STATE_FILE` if it exists.
2. If `state.cache_key == CACHE_KEY` AND `state.cached_at` is within 7 days, treat as a **cache hit**:
   - Print the cached verdict and findings exactly as the previous run produced them.
   - Skip directly to Step 10 (state update is a no-op since nothing changed) and exit.
3. Otherwise, cache miss — continue.

Note: `CACHE_KEY` includes `WT_HASH`, so any change to the working tree (including post-`--fix` edits) invalidates the cache automatically.

### 1e. Convergence check

Read `state.cycle` (default 0 if no state). If `cycle >= 2` AND `FORCE_FRESH` is 0:

```
⚠️ Convergence limit reached (2 cycles).

This branch has been reviewed twice. Further review is unlikely to find
genuinely new issues — if BLOCKERs persist, they are real and need a
different approach (rethink the change, request human review).

Override with --force-fresh to run a fresh full review.
```

Stop. Do not proceed.

If `FORCE_FRESH` is 1: reset `state.cycle = 0` and clear cached findings.

The new cycle number is `state.cycle + 1` (persisted in Step 10).

### 1f. Context Bundle Cache and Freshness Signals

The context bundle (Linear ticket + PR comments + ADR + past devsql sessions) is **cached separately** from the findings. It survives rebases and is invalidated source-by-source via lightweight freshness probes — not by a fixed TTL.

**Cache file**: `$STATE_DIR/${BRANCH_SAFE}.context.json`

**Cache key**: `branch_name + skill_version` (no SHAs — Linear/ADR/sessions are orthogonal to the diff). The bundle survives rebases.

**Hard TTL**: 7 days, used only as a garbage-collector for abandoned PRs. Freshness inside the TTL is decided by signal probes, not the timestamp.

**Schema**:

```json
{
  "key": "<BRANCH_SAFE>_v1",
  "fetched_at": "<ISO timestamp>",
  "freshness_signals": {
    "linear_ticket_id": "NAB-204" | null,
    "linear_updated_at": "2026-05-17T14:22:00Z" | null,
    "github_pr_number": 1234 | null,
    "github_pr_updated_at": "2026-05-18T09:55:00Z" | null,
    "adr_git_sha": "<short sha of last commit touching docs/adr/>" | null,
    "devsql_max_history_ts": 1715300000000 | null,
    "devsql_max_jhistory_ts": 1715300000000 | null
  },
  "bundle_sources": {
    "linear": "<verbatim section>" | null,
    "pr": "<verbatim section>" | null,
    "adr": "<verbatim section>" | null,
    "sessions": "<verbatim section>" | null
  }
}
```

**Probe procedure** (run all 4 probes in parallel — total cost <1s, ~2-5K tokens):

If `FORCE_FRESH` is 1, skip the probes — full re-fetch is forced. Otherwise:

1. **Linear** — extract ticket ID from branch name (same regex as Step 3g). If found, query `updatedAt` only via `linear-cli`. If unavailable or no ticket → signal is `null`.
2. **GitHub PR** — `gh pr view --json updatedAt` for current branch. If no PR → signal is `null`.
3. **ADR** — `git log -1 --format=%H -- docs/adr/ 2>/dev/null` (returns sha or empty). If no `docs/adr/` directory → signal is `null`.
4. **devsql** — for each changed file, run:
   ```sql
   SELECT MAX(timestamp) FROM history WHERE display LIKE '%<file>%';
   SELECT MAX(timestamp) FROM jhistory WHERE display LIKE '%<file>%';
   ```
   Take the global max across all changed files for each table. If `devsql` unavailable → signal is `null`.

**Compare signals to cached values**, source by source:

| Result | Action for that source |
|---|---|
| Cached signal == fresh signal | **Reuse** the cached `bundle_sources.<source>` portion |
| Cached signal != fresh signal | **Re-fetch** this source in Step 3g |
| Cached signal `null` AND fresh signal not `null` | **Fetch** (newly available) |
| Cached signal not `null` AND fresh signal `null` | **Re-fetch** (transient unavailability — don't trust the cache) |
| No cache file present (cold start) | **Fetch all 4 sources** |

Pass the resulting `sources_to_fetch` list (subset of `linear`, `pr`, `adr`, `sessions`) and the cached portions to the context-fetcher in Step 3g.

## Step 2: Get the Diff and Detect Stack

```bash
git diff $BASE_SHA...HEAD --name-only
git diff $BASE_SHA...HEAD
```

Store the diff and changed-file list — they are passed to reviewers.

Detect stack:

```bash
jq -r '.dependencies // {} | keys[]' package.json 2>/dev/null | rg '^(react|next)$'
```

If neither matches, mark `react-reviewer` as skipped.

## Step 3: Parallel Review (Agent Team) with Self-Consistency

### 3a. Create Team

```
TeamCreate  team_name: "gate"  description: "Deterministic quality gate review"
```

### 3b. Create Review Tasks

Create one `TaskCreate` per reviewer. **Skip the React task if the project does not use React/Next.js.**

Each reviewer task `description` MUST be assembled in the order below — **static blocks first, dynamic blocks last**. This ordering is load-bearing for prompt caching: the Anthropic API caches by prefix match, so any reordering or insertion of dynamic content earlier in the prompt invalidates cache hits across passes and across runs. Cf. https://www.anthropic.com/news/prompt-caching.

**Static blocks (order preserved across all reviewers and runs)**:

1. The skill command to invoke (see table below)
2. **Self-consistency instruction**: invoke the assigned skill **3 times** on the same diff. After each pass, parse the findings into the JSON schema below. After 3 passes, perform fuzzy matching (±5 lines, same `rule_id`, same file) to group findings across passes. Drop any finding present in fewer than 2 passes. Emit only findings with `votes >= 2`.
3. The required JSON output schema (see below)
4. The rule-ID enum for this reviewer (see below)
5. Tier classification rules (see below)
6. Boy Scout location classification (see below)
7. Instruction: **Do NOT modify any files. Read-only.**
8. Instruction: write the final JSON to `/tmp/gate-findings-<reviewer-name>.json`
9. Instruction: send a "done" notification to `lead` via `SendMessage` and mark the task `completed`

**Dynamic blocks (last — different on every run)**:

10. The list of `+` lines per file (extracted from the diff — these are the **diff-lines** for Boy Scout classification)
11. The full diff (or changed-file list with read instructions if diff > 50KB)

| Reviewer name | Skill | Rule prefix |
|---|---|---|
| `react-reviewer` (skip if not React) | `/vercel-react-best-practices` | `react-*` |
| `solid-reviewer` | `/applying-solid-principles` | `solid-*` |
| `security-reviewer` | `/security-review` | `security-*` |
| `simplify-reviewer` | `/simplify` | `simplify-*` |
| `slop-reviewer` | `/code-slop` | `slop-*` |
| `context-fetcher` | (no skill — see spec below) | — |

### 3c. Required JSON output schema (per reviewer)

```json
{
  "reviewer": "<reviewer-name>",
  "passes_executed": 3,
  "findings": [
    {
      "rule_id": "<from enum>",
      "file": "<path>",
      "line": <int>,
      "location": "diff-line | adjacent",
      "tier": "BLOCKER | MAJOR | NIT",
      "votes": <2 or 3>,
      "message": "<one-line description>",
      "evidence": "<verbatim code excerpt or specific reference>",
      "suggested_fix": "<concrete change>"
    }
  ]
}
```

### 3d. Rule-ID enums (closed sets — reviewers may only emit these IDs)

| Reviewer | Allowed `rule_id` values |
|---|---|
| `react-reviewer` | `react-missing-key`, `react-stale-closure`, `react-deps-missing`, `react-deps-extra`, `react-no-memo-needed`, `react-effect-misuse`, `react-server-client-mismatch`, `react-hydration-risk`, `react-state-derivation`, `react-other` |
| `solid-reviewer` | `solid-srp`, `solid-ocp`, `solid-lsp`, `solid-isp`, `solid-dip`, `solid-coupling`, `solid-cohesion`, `solid-other` |
| `security-reviewer` | `security-xss`, `security-sql-injection`, `security-injection-other`, `security-secrets-leak`, `security-auth-bypass`, `security-csrf`, `security-ssrf`, `security-path-traversal`, `security-unsafe-deserialization`, `security-other` |
| `simplify-reviewer` | `simplify-dead-code`, `simplify-overengineering`, `simplify-naming`, `simplify-redundant`, `simplify-extract`, `simplify-inline`, `simplify-other` |
| `slop-reviewer` | `slop-defensive-check`, `slop-comment-noise`, `slop-any-cast`, `slop-style-drift`, `slop-unused`, `slop-other` |

### 3e. Tier classification rules (include in each task description)

**BLOCKER** (must fix to merge):
- Bugs or logic errors with concrete repro path
- Security vulnerabilities (verified, not theoretical)
- Performance regressions with measurable impact
- Data loss or migration danger

**MAJOR** (warn, do not block):
- SOLID violations
- Architectural debt introduced by this diff
- Performance concerns without measured impact
- Simplification opportunities with non-trivial size reduction

**NIT** (informational):
- Style preferences
- Minor readability tweaks
- Naming debates
- "Nice to have" improvements

### 3f. Boy Scout location classification (include in each task description)

For each finding, set `location`:

- **`diff-line`**: the issue is on a line marked `+` in the diff (added or modified). Tier may be BLOCKER, MAJOR, or NIT.
- **`adjacent`**: the issue is in a modified file but on a line NOT marked `+` (untouched legacy code). **Cap tier at MAJOR** — never emit BLOCKER for adjacent findings.
- Findings in files not present in the diff: **drop entirely**.

### 3g. Task 6 spec — `context-fetcher`

Goal: assemble a context bundle for Step 6 (context-checker), reusing cached portions whenever the freshness probes (Step 1f) agreed.

The task `description` is built dynamically based on `sources_to_fetch` (the subset of `{linear, pr, adr, sessions}` flagged stale or missing). For each source NOT in `sources_to_fetch`, the cached portion is passed in so the teammate can paste it verbatim into the bundle. **Static blocks first, dynamic blocks last** — same prompt-caching convention as the reviewer tasks.

**Static blocks** (constant across all runs):

1. Read-only directive — Do NOT modify any files.
2. Source specs (each block is conditional — only included if the source is in `sources_to_fetch`):

   **Linear (if stale)**:
   - Detect ticket ID from branch name (patterns: `<prefix>/<TEAM>-<NUM>-<slug>`, `<TEAM>-<NUM>-<slug>`).
   - Fetch issue + all comments via `/linear-cli`.
   - Capture `updatedAt` separately for the freshness signal.
   - If no ticket detected → emit `## Linear\nnot found` and signal `null`.

   **GitHub PR (if stale)**:
   - `gh pr view --json number,title,body,comments,reviews,updatedAt`.
   - Capture body, review comments, conversation comments.
   - Capture `updatedAt` separately for the freshness signal.
   - If no PR → emit `## PR\nnone` and signal `null`.

   **ADR (if stale)**:
   - Read all markdown files under `docs/adr/` (if the directory exists).
   - Filter to ADRs whose body mentions any changed file/symbol.
   - Capture `git log -1 --format=%H -- docs/adr/` for the freshness signal.
   - If no `docs/adr/` → emit `## ADR\nnone` and signal `null`.

   **Past sessions (if stale)**:
   - Use `devsql`. Reliable tables: `history` (Claude Code prompts) and `jhistory` (Codex CLI sessions). `transcripts` is often empty.
   - Per changed file, run:
     ```sql
     SELECT datetime(timestamp/1000, 'unixepoch') AS ts, project, display
     FROM history
     WHERE project LIKE '%<basename of cwd>%'
       AND (display LIKE '%<file path>%' OR display LIKE '%<file basename>%')
     ORDER BY timestamp DESC LIMIT 10;
     ```
     ```sql
     SELECT datetime(timestamp/1000, 'unixepoch') AS ts, display
     FROM jhistory
     WHERE display LIKE '%<file path>%' OR display LIKE '%<file basename>%'
     ORDER BY timestamp DESC LIMIT 10;
     ```
   - Cap at ~80 rows total.
   - Capture `MAX(timestamp)` from each table for the freshness signal.
   - If devsql unavailable → emit `## Past sessions\ndevsql unavailable` and signals `null`.

3. Output format — write the merged bundle to `/tmp/gate-context-bundle.md`:
   ```
   ## Linear
   <issue id, title, status, body, comments — or "not found">

   ## PR
   <number, title, body, review comments, conversation comments — or "none">

   ## ADR
   <relevant ADR excerpts — or "none">

   ## Past Claude Code sessions (per file)
   ### <file/path.ts>
   - <ts> session <id…>: <one-line excerpt>
   ```
4. **Also write** the freshness signals JSON to `/tmp/gate-freshness-signals.json`:
   ```json
   {
     "linear_ticket_id": "...",
     "linear_updated_at": "...",
     "github_pr_number": ...,
     "github_pr_updated_at": "...",
     "adr_git_sha": "...",
     "devsql_max_history_ts": ...,
     "devsql_max_jhistory_ts": ...
   }
   ```
5. Send "done" to `lead` via `SendMessage` and mark task `completed`.

**Dynamic blocks** (passed at the end of the prompt):

6. The list of changed files (extracted from Step 2)
7. The `sources_to_fetch` list (subset of `linear, pr, adr, sessions`)
8. The cached portions for sources NOT in `sources_to_fetch` (verbatim markdown to paste)

**Note**: if `sources_to_fetch` is empty, the teammate just merges the 4 cached portions, writes them to the bundle and signals files, and exits. No external calls.

### 3h. Spawn Teammates (all in parallel)

Spawn all teammates **in a single response** using the `Task` tool with `team_name: "gate"`. **Each teammate's prompt MUST explicitly prescribe the model** — teammates do NOT inherit the lead's model by default (cf. https://code.claude.com/docs/en/agent-teams).

| name | Assigned task | Prescribed model |
|---|---|---|
| `react-reviewer` | React review (skip if not React) | **Opus 4.7** |
| `solid-reviewer` | SOLID review | **Opus 4.7** |
| `security-reviewer` | Security review | **Opus 4.7** |
| `simplify-reviewer` | Simplify review | **Opus 4.7** |
| `slop-reviewer` | Slop review | **Opus 4.7** |
| `context-fetcher` | Context bundle | **Haiku 4.5** |

Reviewers run on Opus because review quality is the load-bearing axis of this skill. The context-fetcher runs on Haiku because its work is mechanical (parse JSON from `gh pr view`, run devsql queries, format markdown) — Haiku is sufficient and ~10× cheaper.

Each teammate's prompt must:
1. Open with the model directive: `Use Opus 4.7 for this task.` (or `Use Haiku 4.5 for this task.` for the context-fetcher) — this is the first line so the team scheduler picks the right model.
2. Instruct the teammate to: check `TaskList`, claim their task via `TaskUpdate` (`status: in_progress`, `owner: <their-name>`)
3. Execute their task as specified (3 passes for reviewers, single pass for context-fetcher)
4. Write output to `/tmp/gate-findings-<name>.json` (or `/tmp/gate-context-bundle.md`)
5. Send `SendMessage` to `lead` with `summary: "<name> done — written to /tmp/gate-findings-<name>.json"`
6. Mark task `completed` via `TaskUpdate`

The lead's model is whatever the user is currently running — no prescription. The lead's role (consolidate JSON, compute verdict, format output) is well within Sonnet/Haiku capability.

## Step 4: Consolidate Findings

### 4a. Wait and Collect

Monitor `TaskList` until all reviewer tasks are `completed`. Read each output file:

- `/tmp/gate-findings-react-reviewer.json` (if spawned)
- `/tmp/gate-findings-solid-reviewer.json`
- `/tmp/gate-findings-security-reviewer.json`
- `/tmp/gate-findings-simplify-reviewer.json`
- `/tmp/gate-findings-slop-reviewer.json`
- `/tmp/gate-context-bundle.md`
- `/tmp/gate-freshness-signals.json` (used in Step 10 to update the context cache)

Do NOT rely on `SendMessage` content for findings — files are the source of truth.

### 4b. Shut Down Team

Send `SendMessage` with `type: "shutdown_request"` to each teammate. Call `TeamDelete`. **Do not delete temp files yet** — Steps 5 and 6 read them.

### 4c. Merge

Concatenate all `findings` arrays. Each finding now has `reviewer`, `rule_id`, `file`, `line`, `tier`, `location`, `votes`, `message`, `evidence`, `suggested_fix`.

### 4d. Detect cross-reviewer overlaps

Group findings by `(file, line ±5)` across reviewers. Two cases:

- **Same `rule_id`** across reviewers (rare but possible): collapse to one item, keep highest tier, merge messages.
- **Different `rule_id`** on overlapping location: keep both, but mark with `conflict_marker: true` if their `suggested_fix` describes contradictory edits (different intent on same code). Display them side-by-side in the output. **No automatic arbitration** — the user decides.

## Step 5: Validator (Anti-Hallucination)

Spawn a single standalone validator via the `Agent` tool (NOT part of the team):

- **subagent_type**: `general-purpose`
- **model**: `sonnet` — mechanical evidence-matching, no need for Opus
- **description**: `Validate finding evidence`
- **prompt**: Provide the validator with:
  1. The consolidated BLOCKER + MAJOR list (skip NIT — too noisy and not gate-relevant)
  2. Each finding's `evidence` and `suggested_fix`
  3. The relevant file excerpts (read each file once, include surrounding context)
  4. Decision rule per finding:
     - **VERIFIED**: evidence matches the cited code, the issue is real, the suggested fix addresses it
     - **DOWNGRADE**: evidence is plausible but the impact is debatable — keep the finding but force tier to MAJOR (if BLOCKER) or NIT (if MAJOR)
     - **DROP**: evidence does not match the code, or the finding is hallucinated
  5. Required output: JSON array with `{file, line, rule_id, verdict: VERIFIED|DOWNGRADE|DROP, reason}` per finding
  6. Instruction: **read-only — do NOT edit any files**

Apply the validator verdicts:
- VERIFIED → keep tier as-is
- DOWNGRADE → reduce tier by one level (BLOCKER→MAJOR, MAJOR→NIT)
- DROP → remove from list entirely

## Step 6: Context Check

Spawn a single standalone `context-checker` via the `Agent` tool:

- **subagent_type**: `general-purpose`
- **model**: `sonnet` — semantic matching of findings against bundle text, Opus not required
- **description**: `Check findings against historical context`
- **prompt**: Provide:
  1. The post-validator finding list (BLOCKER + MAJOR; skip NIT)
  2. The full content of `/tmp/gate-context-bundle.md`
  3. Decision rule per finding:
     - **OK** — no contradiction, or bundle silent on the topic
     - **CONFLICT** — bundle contains evidence (issue comment, PR review, past session) that this code was written this way *on purpose*
     - **UNCERTAIN** — bundle mentions the file/symbol but intent is ambiguous
  4. Required output: JSON array with `{file, line, rule_id, verdict: OK|CONFLICT|UNCERTAIN, source: linear|pr|session|none, citation: "<≤240 chars>", reason}`
  5. Instruction: **read-only — do NOT edit any files**

**Important**: do NOT include freshness timestamps (Linear `updatedAt`, gh PR `updated_at`, devsql `MAX(timestamp)`) in this prompt. Those values change on every run and would break prompt caching for the checker. They live in the state file (Step 1f), not in the agent prompt.

Apply verdicts based on `--fix` flag:

- **With `--fix` (strict)**: `OK` allows auto-apply (Step 8). `UNCERTAIN` and `CONFLICT` block auto-apply for that finding — they stay in the displayed list with a badge but are NOT auto-applied.
- **Without `--fix` (permissive)**: nothing is auto-applied anyway. Add a badge to each finding:
  - `OK` → no badge
  - `UNCERTAIN` → `❔ ambiguous historical context`
  - `CONFLICT` → `⚠️ conflicts with past decision` + citation

The verdict computation in Step 7 is unaffected — context check influences display and `--fix` behavior, not the PASS/FAIL gate.

## Step 7: Compute Verdict

Count findings by tier (post-validator, post-context-check):

| Verdict | Condition | Mergeable? |
|---|---|---|
| **PASS** | 0 BLOCKER, 0 MAJOR, 0 NIT | Yes |
| **PASS WITH NOTES** | 0 BLOCKER, ≥1 MAJOR or NIT | **Yes** — MAJOR/NIT are informational only |
| **FAIL** | ≥1 BLOCKER | No — fix BLOCKERs first |

Display:

```
### Gate Verdict: <PASS | PASS WITH NOTES | FAIL>

Cycle: <N>/2
Diff: <N> files, +<add>/-<del>

BLOCKER: <N>
MAJOR:   <N>
NIT:     <N>
```

For PASS / PASS WITH NOTES, append explicitly:

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

### [security-reviewer] security-sql-injection
- `src/db/users.ts:42` (diff-line) [votes: 3/3]
  message: User input concatenated into raw SQL query
  evidence: `db.query("SELECT * FROM users WHERE id = " + req.params.id)`
  fix: Use parameterized query: `db.query("SELECT * FROM users WHERE id = $1", [req.params.id])`

## MAJOR

### [solid-reviewer] solid-srp
- `src/services/booking.ts:120` (diff-line) [votes: 2/3] ❔ ambiguous historical context
  message: BookingService now handles 4 unrelated responsibilities
  evidence: …
  fix: Extract pricing logic into PricingCalculator
  context: Linear NAB-204 mentions "BookingService is the gateway, by design"

## NIT

### [slop-reviewer] slop-defensive-check
- `src/utils/parse.ts:15` (adjacent) [votes: 2/3]
  message: Null check on guaranteed-non-null parameter
  …
```

Conflicts (from Step 4d) are rendered with both findings adjacent and a `⚡ conflicting suggestions` marker.

## Step 8: Apply Fixes (only if `--fix`)

If `--fix` is NOT set: skip directly to Step 9.

If `--fix` is set:

1. Filter the finding list to only `tier == BLOCKER` AND `validator_verdict == VERIFIED` AND `context_verdict == OK`
2. For each, apply the `suggested_fix` using the Edit tool
3. After all edits, run any project formatter found in `package.json` scripts (`format`, `prettier`, `lint:fix`) — best-effort, non-blocking on failure
4. Print summary: `Applied <N> BLOCKER fixes. Working tree is dirty — review with 'git diff' and commit manually.`

**Never auto-commit. Never auto-push.**

## Step 9: Post-Fix Validator (conditional)

Run only if **all three** conditions are true:
- `--fix` was set
- ≥2 BLOCKER fixes were applied in Step 8
- Step 8 actually modified files

Spawn a single standalone validator via the `Agent` tool:

- **subagent_type**: `general-purpose`
- **model**: `sonnet` — semantic diff review, no need for Opus
- **description**: `Post-fix semantic review`
- **prompt**: Provide:
  1. `git diff <BASE_SHA>...HEAD` (full branch diff including applied fixes)
  2. The list of fixes applied
  3. Role: read-only review checking for:
     - Fixes that break each other (partial renames, inconsistent refactors)
     - Fixes that reintroduce a pre-existing issue
     - Applied changes whose effect does not match their stated intent
  4. Required output (exactly one):
     - `APPROVED` (one line)
     - `ISSUES_FOUND:` followed by `- file:line — description` bullets
  5. Instruction: **read-only — do NOT edit any files**

If `APPROVED` → continue.

If `ISSUES_FOUND` → display the issue list and `git diff --stat`, then use `AskUserQuestion`:
- **Proceed anyway** — leave changes as-is
- **Rollback** — `git restore .` to discard applied fixes
- **Inspect** — exit, leave working tree dirty

## Step 10: Persist State and Cleanup

### 10a. Findings cache

Write `$STATE_FILE` (`<branch_safe>.json`):

```json
{
  "cache_key": "<HEAD_SHA>_<BASE_SHA>_<WT_HASH>_v1",
  "cached_at": "<ISO timestamp>",
  "cycle": <new cycle number>,
  "verdict": "PASS | PASS WITH NOTES | FAIL",
  "findings": [ … full finding list with all metadata … ],
  "applied_fixes": [ … list of fixes applied if --fix, else [] ]
}
```

### 10b. Context bundle cache

Write `$STATE_DIR/${BRANCH_SAFE}.context.json` (separate file from the findings cache — survives rebases). Read `/tmp/gate-freshness-signals.json` for the new signals, and `/tmp/gate-context-bundle.md` for the bundle (split it into the four sections to populate `bundle_sources`):

```json
{
  "key": "<BRANCH_SAFE>_v1",
  "fetched_at": "<ISO timestamp>",
  "freshness_signals": { ... from /tmp/gate-freshness-signals.json ... },
  "bundle_sources": {
    "linear":   "<verbatim ## Linear section>" | null,
    "pr":       "<verbatim ## PR section>" | null,
    "adr":      "<verbatim ## ADR section>" | null,
    "sessions": "<verbatim ## Past Claude Code sessions section>" | null
  }
}
```

If a source was reused from cache (not re-fetched), keep the existing portion as-is.

### 10c. Cleanup temp files

```bash
rm -f /tmp/gate-findings-*.json /tmp/gate-context-bundle.md /tmp/gate-freshness-signals.json
```

## Execution Notes

- **Requires**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- **Coexists** with the legacy `quality-gate` skill (kept as baseline / comparison point)
- **Reviewer roster**: 5 reviewers (4 if not React) + `context-fetcher`, all in parallel. Each reviewer self-loops 3× internally and votes — single team output is the post-vote JSON.
- **Model assignment** (per role):
  - Reviewers (Opus 4.7) — review quality is the load-bearing axis
  - `context-fetcher` (Haiku 4.5) — mechanical parsing, ~10× cheaper
  - Standalone agents — Sonnet 4.6 (validator, context-checker, post-fix-validator)
  - Lead — whatever the user is running, no prescription
  - Teammates do NOT inherit lead's model — every teammate prompt prescribes its model explicitly
- **Standalone agents** (validator, context-checker, post-fix-validator): spawned via `Agent`, NOT part of the team
- **All review and standalone agents are read-only** — only the lead applies fixes (and only with `--fix`)
- **Convergence is the stopping criterion**: 2 cycles max per branch, override via `--force-fresh`
- **Two cache layers**:
  - **Findings cache** (`<branch>.json`): keyed on `HEAD_SHA + BASE_SHA + WT_HASH + skill_version`. Hit = zero LLM calls.
  - **Context bundle cache** (`<branch>.context.json`): keyed on `branch_name + skill_version`. Survives rebases. Invalidated source-by-source via 4 freshness probes (Linear `updatedAt`, gh PR `updated_at`, ADR git sha, devsql `MAX(timestamp)`). Fresh sources are reused verbatim; stale sources are re-fetched selectively.
  - Both caches share a hard 7-day TTL as a GC for abandoned PRs.
- **Prompt caching is load-bearing**: every agent prompt is built **static-first, dynamic-last** (instructions/schemas/rules before diff/findings). Reordering breaks Anthropic's prefix-match cache and inflates cost. Freshness timestamps live in the state file, never in agent prompts. Cf. https://www.anthropic.com/news/prompt-caching.
- **Boy Scout asymmetry**: adjacent legacy code can be flagged (MAJOR/NIT) but never blocks the gate
- **Tier semantics are load-bearing**: only BLOCKER affects the verdict. MAJOR and NIT are informational.
- **No auto-arbitration** — conflicting suggestions are displayed side-by-side, user decides
- **No auto-commit** — `--fix` modifies files only; commit is always manual
