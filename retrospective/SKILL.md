---
name: retrospective
description: Reflect on the work done on the current branch vs main — mine devsql history, git log, and session transcripts for back-and-forths, rollbacks, and wasted time, then interview the user to distill durable lessons into a local-ignored CLAUDE.local.md.
argument-hint: "[base-branch]"
---

# Retrospective

Reflect on how the work on the current branch actually went — not what was delivered, but what cost time — and turn that into durable guidance so future sessions avoid the same back-and-forths.

**Arguments:** `$0` = `[base-branch]` (optional, default auto-detected: `develop` for mk-copilot, else `main` / `master`).

## 0. Preconditions

```bash
pwd
git rev-parse --abbrev-ref HEAD
```

- Do not run on the base branch itself (main/master/develop). If on base, stop and ask the user which branch to retrospect.
- Verify `devsql` is installed: `which devsql`. If missing, continue without devsql signals and note this to the user.

## 1. Establish Scope

Determine base branch (`BASE`):
- If `$0` provided, use it.
- Else detect: `develop` if repo has one and name matches mk-copilot pattern, else `main`, else `master`.

Determine branch timeframe:
```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
FIRST_COMMIT_TS=$(git log --reverse --format=%ct "$BASE..HEAD" | head -1)
LAST_COMMIT_TS=$(git log -1 --format=%ct HEAD)
BRANCH_POINT_TS=$(git log -1 --format=%ct $(git merge-base "$BASE" HEAD))
```

Use `FIRST_COMMIT_TS` (or `BRANCH_POINT_TS` if no commits yet) through "now" as the analysis window. Convert to ms for devsql (`* 1000`).

Report to user:
- Branch, base, timeframe (human-readable), number of commits on branch.

## 2. Mine Signals (in parallel where independent)

Collect evidence. Present counts first, then details on request.

### 2a. Git signals

```bash
# Commits on branch
git log --format="%h %ai %s" "$BASE..HEAD"

# Reverts / fix-ups / "revert" / "undo" in messages
git log --format="%h %s" "$BASE..HEAD" | rg -i "revert|undo|rollback|fixup|oops|wip|tmp"

# Force pushes / resets visible in reflog (last 2 weeks)
git reflog --date=iso --since="2 weeks ago" | rg -i "$BRANCH|reset|amend|force"

# Files touched multiple times (churn)
git log --name-only --format= "$BASE..HEAD" | sort | uniq -c | sort -rn | head -20
```

### 2b. devsql prompt signals

Query history within the branch window, filtered to this project. `history.timestamp` is milliseconds.

```bash
PROJECT=$(pwd)
START_MS=$((FIRST_COMMIT_TS * 1000))

devsql "SELECT datetime(timestamp/1000,'unixepoch','localtime') as t, substr(display,1,200) as d
FROM history
WHERE project = '$PROJECT'
  AND timestamp > $START_MS
ORDER BY timestamp ASC" --format md
```

Then pull the subset matching frustration/rollback patterns:

```bash
devsql "SELECT datetime(timestamp/1000,'unixepoch','localtime') as t, substr(display,1,300) as d
FROM history
WHERE project = '$PROJECT'
  AND timestamp > $START_MS
  AND (LOWER(display) LIKE '%rollback%'
       OR LOWER(display) LIKE '%revert%'
       OR LOWER(display) LIKE '%undo%'
       OR LOWER(display) LIKE '%didn''t work%'
       OR LOWER(display) LIKE '%doesn''t work%'
       OR LOWER(display) LIKE '%not working%'
       OR LOWER(display) LIKE '%broke%'
       OR LOWER(display) LIKE '%still%fail%'
       OR LOWER(display) LIKE '%try again%'
       OR LOWER(display) LIKE '%go back%'
       OR LOWER(display) LIKE '%nope%')
ORDER BY timestamp ASC" --format md
```

Also count total prompts and distinct sessions in window:

```bash
devsql "SELECT COUNT(*) as prompts FROM history WHERE project='$PROJECT' AND timestamp > $START_MS"
```

### 2c. Tool-call failures in session transcripts

Sessions live at `~/.claude/projects/<slug>/*.jsonl` where `<slug>` is the project path with `/` → `-`.

```bash
SLUG=$(echo "$PROJECT" | sed 's|/|-|g')
SESSION_DIR="$HOME/.claude/projects/$SLUG"

# Sessions touched in the window
fd -e jsonl . "$SESSION_DIR" -x stat -f "%m %N" {} | awk -v start="$FIRST_COMMIT_TS" '$1 >= start {print $2}'
```

For each session file in range, count tool errors and test failures:

```bash
jq -r 'select(.type=="tool_result") | .message.content[]? | select(.type=="tool_result" and .is_error==true) | .content[0].text // ""' "$SESSION_FILE" 2>/dev/null | wc -l
```

Also grep for test failures, typecheck errors, lint errors in tool results:

```bash
rg -c "FAIL |failed|✘|error TS|ESLint" "$SESSION_FILE"
```

### 2d. Time-to-complete

- Elapsed wall time: `LAST_COMMIT_TS - BRANCH_POINT_TS`.
- Active prompt span: `MAX(history.timestamp) - MIN(history.timestamp)` in window.
- Session count: distinct jsonl files touched in window.

### 2e. Rework signals (cross-commit / cross-session)

Rework = later commits or sessions that exist to fix a previous iteration *on the same branch*. This is distinct from 2a's churn (which doesn't tell you *why*) and from 2b's rollback grep (which misses the quiet vocabulary: `fix`, `actually`, `follow-up`, `address feedback`, `forgot`).

#### 2e.1 Cross-commit rework (always runs — git only)

```bash
# Explicit fixups / squash markers
git log --format="%h %s" "$BASE..HEAD" | rg -i '^\w+ (fixup!|squash!|amend!)'

# Rework vocabulary in commit messages
git log --format="%h %s" "$BASE..HEAD" \
  | rg -i '\b(actually|properly|forgot|follow[- ]?up|address(ed)? (review|feedback|comments?)|revisit|redo|re-?work|take 2|second pass|fix(es|ed)? (previous|prior|earlier))\b'

# Same-scope rewrites: conventional-commit scope pairs like feat(x) → fix(x)
git log --reverse --format="%h %s" "$BASE..HEAD" \
  | rg '^[0-9a-f]+ \w+\([^)]+\):' \
  | awk '{
      match($0, /\w+\(([^)]+)\):/, m)
      scope=m[1]
      if (scope in seen) print seen[scope] " → " $0
      seen[scope]=$0
    }'
```

Then for each file with churn ≥ 2 (from 2a), list consecutive commit pairs on that file where the later commit lands within 24h of the prior *and* the later message matches rework vocabulary or shares the same scope prefix. Output per scope/file: `N rework commits over M hours — {hashes}`.

#### 2e.2 Cross-session rework (needs jsonl; devsql optional)

Order sessions from 2c by earliest timestamp. For each adjacent pair `(N, N+1)`:

```bash
# First user prompts of session N+1 (rework-opening vocabulary)
jq -r 'select(.type=="user") | .message.content' "$SESSION_FILE_NEXT" 2>/dev/null \
  | head -2 \
  | rg -i '\b(still|didn''t work|doesn''t work|not working|broke|broken|follow[- ]?up|actually|revisit|go back|that change|earlier change|previous (commit|change|attempt))\b'

# Files edited in each session (Edit / Write tool_use entries)
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use" and (.name=="Edit" or .name=="Write")) | .input.file_path' "$SESSION_FILE" 2>/dev/null | sort -u
```

Compute the intersection of edited files between N and N+1. A session pair is **rework** if:
- N+1's opening prompt matches the vocabulary above, OR
- File overlap ≥ 2 files AND N+1 opens within 24h of N's last activity.

Report per rework session: `opened with "<first prompt, first 80 chars>", re-touched <K> files from prior session`.

#### 2e.3 Thresholds & report integration

- Compute `REWORK_COMMITS` (union of 2e.1 detections, deduped by hash) and `REWORK_SESSIONS` (count of flagged session pairs).
- If `REWORK_COMMITS ≥ 2` OR `REWORK_SESSIONS ≥ 1`, emit a dedicated **Rework** bullet cluster in §3's "What went sideways", with evidence (hashes / session ids / first-prompt snippets).
- If > 10 rework items, show top 10 by recency.

#### 2e.4 Silent fallbacks

- No devsql → still run 2e.1 and compute file-overlap in 2e.2 from jsonl.
- No jsonl → skip 2e.2 entirely and note this in the report.
- 2e.1 always runs (git-only).

## 2f. Classify Signals by Harness Subsystem

For each cluster identified in 2a–2e, tag it with the most likely harness subsystem using these heuristics:

- **Instructions** — wrong stack version, naming/convention violation, "didn't know about ADR X", rework vocab (`actually`, `properly`, `forgot`) on the same scope
- **Tools** — `command not found`, `permission denied`, agent attempted action but lacked capability
- **Environment** — dep install failures, version mismatches, env var missing, "works on my machine" in CI logs
- **State** — session N+1 opens with "still broken / didn't work" + re-touches files from N; re-exploration of repo structure across sessions
- **Feedback** — error caught only in CI / review (not locally), agent declared "done" prematurely, force-push or amend storms, repeated "doesn't work / try again" prompts

Output a `subsystem_map.json` in memory: `{ cluster_id: { subsystem, confidence: high|medium|low, evidence: [...] } }`.
Low-confidence classifications go to the user in §4.

## 3. Synthesize the Report

Produce a concise report with these sections. Do NOT persist anything yet.

```markdown
## Retrospective — <branch> vs <base>

**Timeframe:** <first commit> → now (<X days, Y hours>)
**Volume:** <N> commits, <M> prompts, <S> sessions
**Cost signals:** <K> rollback-flavored prompts, <R> revert commits, <T> tool-call failures, <F> high-churn files, <Rw> rework commits, <Rs> rework sessions

### What went sideways
- <rollback / retry cluster #1> — <what was attempted, what broke, evidence link>
- <rollback / retry cluster #2> — ...
- **Rework** (only if `Rw ≥ 2` or `Rs ≥ 1`) — <scope/file> fixed in <N> follow-up commits over <M>h; session <id> opened with "<snippet>" and re-touched <K> files from prior session

### Harness diagnosis

| Subsystem | Incidents | Evidence |
|---|---|---|
| Instructions | <N> | <hashes / sessions> |
| Tools | <N> | … |
| Environment | <N> | … |
| State | <N> | … |
| Feedback | <N> | … |

**Bottleneck this branch:** <subsystem> (<N> incidents, <%>)

### Root causes (hypotheses, grouped by subsystem)

**Instructions**
- <missing rule that would have prevented the cluster>

**Feedback**
- <missing verification command>

(skip subsystems with 0 incidents)

### What would have helped from the start
- <instruction / CLAUDE.md rule that would have prevented the biggest cluster>
- <skill or subagent that should have been invoked earlier>
- <doc / link that was discovered only at the end>
```

## 4. Interview — Distill Durable Lessons

For each root cause / "would have helped" item in the report, ask the user via AskUserQuestion whether to keep it, and if so, how to phrase the rule. Keep it tight — 3-5 candidate lessons max. For each kept lesson, collect:

- **Rule** (imperative, one line)
- **Why** (what incident it came from — keeps future-you from second-guessing)
- **Scope** (does it apply to this repo only? this kind of task? always?)

Skip lessons the user rejects. Do not argue — the user is the filter.

## 5. Persist to Local-Ignored CLAUDE.local.md

```bash
CLAUDE_LOCAL="$(git rev-parse --show-toplevel)/CLAUDE.local.md"
```

Ensure it's gitignored:

```bash
if ! git check-ignore -q "$CLAUDE_LOCAL" 2>/dev/null; then
  # Add to .gitignore if not already ignored
  grep -qxF 'CLAUDE.local.md' "$(git rev-parse --show-toplevel)/.gitignore" 2>/dev/null \
    || echo 'CLAUDE.local.md' >> "$(git rev-parse --show-toplevel)/.gitignore"
fi
```

If `CLAUDE.local.md` does not exist, create it with a header. Otherwise append a new dated section:

```markdown
## Lessons — <YYYY-MM-DD> — <branch>

### <Rule title>
**Rule:** <imperative one-liner>
**Why:** <incident / evidence>
**Scope:** <when this applies>

### <next rule...>
```

Never overwrite existing content. Always append.

## 6. Close Out

Print:
- Path to the updated `CLAUDE.local.md`
- Number of lessons added
- One-line summary of the biggest cost signal from the branch

Suggest (but do not execute) follow-ups:
- "Promote rule X to global `~/.claude/CLAUDE.md` if it applies beyond this repo."
- "Consider encoding rule Y as a pre-commit hook or skill."

## 6.5. Cross-Retrospective Aggregation

Parse all prior `## Lessons —` sections in `CLAUDE.local.md` from the last 30 days. Count `**Subsystem:**` tags. Render an ASCII bar chart of the distribution. If the top subsystem accounts for ≥40% of lessons, flag it as the systemic bottleneck and surface up to 3 most-recurring remedy suggestions.

## Execution Notes

- **Do not** run git destructive commands. Read-only analysis.
- **Do not** push, commit, or modify tracked files — the only file touched is `CLAUDE.local.md` (gitignored) and possibly `.gitignore` to add that entry.
- **Parallelize** Step 2 sub-signals (git / devsql / transcripts) — they are independent.
- **Truncate**: if a signal yields >50 rows, summarize counts and show top 10 by recency.
- **Silent fallbacks**: if devsql is missing, skip 2b and note it. If session jsonl parsing fails, skip 2c. Always produce a report from whatever signals succeeded.
- **One retrospective per branch per day** is the typical cadence — if `CLAUDE.local.md` already has an entry for today+branch, ask the user whether to append a new section or merge into the existing one.
