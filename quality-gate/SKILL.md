---
name: quality-gate
description: Run parallel quality reviews (React, SOLID, Security, Simplification, Slop) on branch changes and auto-fix issues
argument-hint: "[base-branch]"
---

# Quality Gate

!IMPORTANT: Follow this process exactly. Do not skip steps.

**Arguments:** `$0` (optional) — base branch to diff against. If omitted, auto-detect.

## Step 0: Verify Dependencies

This skill invokes four external skills plus one Claude Code built-in. Before doing anything else, verify each is installed at `~/.claude/skills/<name>/SKILL.md` (or as a built-in). `simplify` is a Claude Code built-in command and does not require installation.

Check each path in a single shell call:

```bash
for s in vercel-react-best-practices applying-solid-principles security-review code-slop; do
  [ -f ~/.claude/skills/$s/SKILL.md ] && echo "OK  $s" || echo "MISS $s"
done
```

If any report `MISS`, stop and tell the user which skills are missing with the exact install command for each. Do not proceed until the user confirms they are installed.

| Skill | Install command |
|-------|-----------------|
| `vercel-react-best-practices` | `npx skills add https://github.com/vercel-labs/agent-skills --skill vercel-react-best-practices -g` |
| `applying-solid-principles` | `npx skills add https://github.com/BenjaminG/ai-skills --skill applying-solid-principles -g` |
| `security-review` | `npx skills add https://github.com/getsentry/skills --skill security-review -g` |
| `code-slop` | `npx skills add https://github.com/BenjaminG/ai-skills --skill code-slop -g` |
| `simplify` | Built-in to Claude Code — no install needed |

If the project does not use React/Next.js, `vercel-react-best-practices` is optional (Task 1 in Step 2 is skipped anyway).

## Step 1: Get the Diff

Detect the base branch:
```bash
git rev-parse --verify main >/dev/null 2>&1 && echo "main" || (git rev-parse --verify master >/dev/null 2>&1 && echo "master" || echo "develop")
```

Then get the full diff and changed file list:
```bash
git diff <base>...HEAD --name-only
git diff <base>...HEAD
```

Store the diff output — you will pass it to review agents.

Also detect the project stack:
```bash
# Check if React/Next.js project
cat package.json 2>/dev/null | jq -r '.dependencies // {} | keys[]' | grep -E '^(react|next)$'
```

## Step 2: Parallel Review (Agent Team)

### 2a. Create Team

```
TeamCreate  team_name: "quality-gate"  description: "Parallel quality review of branch changes"
```

### 2b. Create Review Tasks

Create one `TaskCreate` per review dimension. **Skip Task 1 if the project does not use React/Next.js.**

Each task `description` MUST include:
1. The full diff from Step 1 (if diff exceeds ~50KB, list changed files and instruct teammate to read files directly)
2. The list of changed files
3. The skill command to invoke and review instructions (see table below)
4. The classification rules (see below)
5. The required output format (see below)
6. Instruction: **Do NOT modify any files. Report findings only.**
7. Instruction: Write the full findings to `/tmp/quality-gate-findings-<reviewer-name>.md` using the Write tool (e.g. `/tmp/quality-gate-findings-solid-reviewer.md`)
8. Instruction: Send a brief "done" notification to the lead via `SendMessage` with `type: "message"` and `recipient: "lead"` (the lead will read findings from the file, no need to include full findings in the message)
9. Instruction: Mark task completed via `TaskUpdate` with `status: "completed"` after sending findings

| Task | subject | activeForm | Skill command & instructions |
|------|---------|------------|------------------------------|
| 1 | Review React/Next.js best practices | Reviewing React best practices | `/vercel-react-best-practices Review ONLY the changed code in the diff against the rules. Categorize each finding as FIX or NITPICK` |
| 2 | Review SOLID principles | Reviewing SOLID principles | `/applying-solid-principles Review ONLY the changed code in the diff against SOLID principles and clean code practices. Categorize each finding as FIX or NITPICK` |
| 3 | Review security | Reviewing security | `/security-review Review ONLY the changed code in the diff against the security checklist. Categorize each finding as FIX or NITPICK` |
| 4 | Review simplification opportunities | Reviewing simplification | `/simplify Review ONLY the changed code in the diff for simplification opportunities (clarity, consistency, maintainability). Categorize each finding as FIX or NITPICK. Do NOT modify any files — report only.` |
| 5 | Review code slop | Reviewing code slop | `/code-slop` but **override**: Do NOT modify any files. Instead, identify all slop issues and report them in FIX/NITPICK format below. |

### 2c. Spawn Teammates (all in parallel)

Spawn all teammates **in a single response** using the `Task` tool with `team_name: "quality-gate"` and each teammate's `name`:

| name | Assigned task |
|------|---------------|
| `react-reviewer` | Task 1 (skip if not React) |
| `solid-reviewer` | Task 2 |
| `security-reviewer` | Task 3 |
| `simplify-reviewer` | Task 4 |
| `slop-cleaner` | Task 5 |

Each teammate's prompt must instruct them to:
1. Check `TaskList` and claim their assigned task via `TaskUpdate` with `status: "in_progress"` and `owner: "<their-name>"`
2. Invoke the designated skill via the `Skill` tool with the review instructions
3. Format findings per the output format below
4. Write the full formatted findings to `/tmp/quality-gate-findings-<their-name>.md` using the Write tool (e.g. `/tmp/quality-gate-findings-solid-reviewer.md`)
5. Send a brief "done" notification to the lead via `SendMessage` with `type: "message"`, `recipient: "lead"`, and `summary: "<reviewer-name> done — findings written to /tmp/quality-gate-findings-<their-name>.md"`
6. Mark task completed via `TaskUpdate` with `status: "completed"`

### 2d. Assign Tasks

After spawning, assign each task to its teammate via `TaskUpdate` with `owner: "<teammate-name>"`.

### Classification Rules (include in each task description)

**FIX** (will be auto-applied):
- Bugs or logic errors
- Security vulnerabilities
- Performance issues with measurable impact
- Clear violations of critical rules
- Obvious simplifications that reduce complexity without trade-offs

**NITPICK** (user decides):
- Style preferences or minor readability tweaks
- Debatable architectural choices
- Low-impact optimizations
- "Nice to have" improvements

### Required Output Format (include in each task description)

```
## FIX
- `file/path.ts:42` — [RULE-ID] Description of the issue. Suggested fix: <concrete suggestion>
- `file/path.ts:85` — [RULE-ID] Description. Suggested fix: <suggestion>

## NITPICK
- `file/path.ts:15` — [RULE-ID] Description. Suggestion: <suggestion>

## NO ISSUES
(use this section if nothing found in a category)
```

If no issues at all, return: `No issues found.`

## Step 3: Consolidate Findings and Tear Down Team

### 3a. Collect Results

Monitor `TaskList` until all review tasks reach `completed` status. Once all tasks are `completed`, read findings from each reviewer's output file using the Read tool:

- `/tmp/quality-gate-findings-solid-reviewer.md`
- `/tmp/quality-gate-findings-security-reviewer.md`
- `/tmp/quality-gate-findings-simplify-reviewer.md`
- `/tmp/quality-gate-findings-slop-cleaner.md`
- `/tmp/quality-gate-findings-react-reviewer.md` (if spawned)

Do NOT rely on `SendMessage` content for findings — those are "done" pings only. The files are the source of truth.

### 3b. Shut Down Team

Send `SendMessage` with `type: "shutdown_request"` to each teammate. After all teammates confirm shutdown, call `TeamDelete`. Then clean up temp files:

```bash
rm -f /tmp/quality-gate-findings-*.md
```

### 3c. Consolidate and Detect Conflicts

1. Collect all **FIX** items across all reviewers
2. Group by `file:line`
3. For each group with ≥2 FIX items, classify the group:
   - **Duplicate**: suggestions describe the same edit (same intent, same code outcome) → collapse to one item, keep the most specific wording
   - **Conflict**: suggestions describe *different* edits on the same location (e.g., SOLID says "extract into hook", Simplify says "inline it") → flag as a conflict candidate
4. If any conflict candidates exist → proceed to **Step 3d (Arbitrate)**
5. If no conflicts → skip Step 3d and proceed directly to Step 4

Once the final FIX list is settled (after Step 3d if needed), display the summary:

```
### Quality Gate Results

**Fixes to auto-apply:** N items
- [React] file:line — description (x items)
- [SOLID] file:line — description (x items)
- [Security] file:line — description (x items)
- [Simplify] file:line — description (x items)
- [Slop Cleaner] file:line — description (x items)
**Conflicts arbitrated:** N items   ← include only if Step 3d ran
**Nitpicks for review:** N items
```

## Step 3d: Arbitrate Conflicts (conditional)

**Skip this step entirely if Step 3c found zero conflicts.**

Spawn a single standalone arbitrator via the `Agent` tool (NOT part of the team):

- **subagent_type**: `general-purpose`
- **description**: `Arbitrate FIX conflicts`
- **prompt**: Provide the arbitrator with:
  1. The conflict groups only (not all findings) — each group is one `file:line` with the competing FIX items from different reviewers, including the reviewer name and their suggested fix
  2. The relevant file excerpts (read each conflicted file's surrounding context and include it in the prompt)
  3. The fixed priority chain: **Security > Correctness > SOLID > Simplify > Style**. Within the same tier, prefer the fix with the smallest blast radius (fewer lines changed, no new abstractions)
  4. Instruction: return a JSON-like block per conflict with `file:line`, `winner: <reviewer-name>`, `chosen_fix: <verbatim fix>`, `reason: <one sentence>`. Optionally, if two fixes are compatible and can be merged, return `merged` instead with the combined edit
  5. Instruction: **read-only — do NOT edit any files**

Merge the arbitrator's winning fixes back into the FIX list (replacing the conflict groups). Non-conflicted FIX items pass through unchanged. Record the count for the summary line `**Conflicts arbitrated:** N`.

## Step 4: Auto-Fix

Apply all FIX items to the codebase:
- Read each affected file
- Apply the suggested fixes using the Edit tool
- After all fixes, run the project's linter/formatter if configured (check package.json scripts for lint/format)

## Step 5: Present Nitpicks

If there are nitpicks, display them grouped by category and use AskUserQuestion:

```
### Nitpicks for your review

**React/Next.js:**
- `file:line` — description — suggestion

**SOLID:**
- `file:line` — description — suggestion

**Security:**
- `file:line` — description — suggestion

**Simplification:**
- `file:line` — description — suggestion

**Slop Cleaner:**
- `file:line` — description — suggestion
```

Ask: "Which nitpicks should I apply?" with options:
- All of them
- None
- Let me pick (then list individually)

## Step 6: Apply Selected Nitpicks

Apply whichever nitpicks the user selected.

## Step 7: Post-Fix Validation

**Run this step only if any changes were applied in Step 4 or Step 6.** Skip it if no fixes and no nitpicks were applied.

Spawn a single standalone validator via the `Agent` tool (NOT part of the team):

- **subagent_type**: `general-purpose`
- **description**: `Validate post-fix diff`
- **prompt**: Provide the validator with:
  1. The output of `git diff <base>...HEAD` (the full branch diff, including the applied fixes and nitpicks)
  2. The list of FIX + nitpick items that were applied (from Step 4 and Step 6)
  3. Role: read-only semantic review of the final diff. Check for:
     - Fixes that break another fix (e.g., partial renames, inconsistent refactors across files)
     - Fixes that reintroduce an issue the original diff was meant to address
     - Linter/formatter changes that masked a real problem
     - Applied changes that do not match their stated intent (spot-check a sample)
  4. Required output format — exactly one of:
     - `APPROVED` on the first line, nothing else required
     - `ISSUES_FOUND:` on the first line, followed by a bulleted list of `- file:line — problem description`
  5. Instruction: **read-only — do NOT edit any files**

**If the validator returns `APPROVED`:** proceed to Step 8.

**If the validator returns `ISSUES_FOUND`:** display the issue list and `git diff --stat`, then use `AskUserQuestion` with:
- **Proceed anyway** — commit as-is (go to Step 8)
- **Rollback fixes** — run `git restore .` to discard all applied fixes and nitpicks, then abort the skill and report which validator issues were flagged
- **Let me review** — exit without committing, leave the working tree dirty so the user can inspect and edit

## Step 8: Commit & Push (if changes made)

If any changes were applied (fixes or nitpicks) and validation passed or the user chose to proceed:

```bash
git add .
git commit -m "refactor: apply quality gate fixes"
```

If a remote branch exists and the branch was already pushed:
```bash
git push
```

## Execution Notes

- **Requires**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` environment variable in settings
- **Agent roster**: 4–5 parallel team reviewers (skip react-reviewer if not a React project) + up to 2 sequential standalone specialists (`conflict-arbitrator` conditional, `post-fix-validator` runs whenever changes were applied)
- **Standalone specialists** (`conflict-arbitrator`, `post-fix-validator`) are spawned via the `Agent` tool and are NOT part of the `quality-gate` team — no TeamCreate/TeamDelete coupling, no shared TaskList
- **Arbitrator fires only when ≥1 conflict is detected in Step 3c** — zero cost when reviewers agree
- **Arbitrator priority** (deterministic): **Security > Correctness > SOLID > Simplify > Style**; within the same tier prefer the fix with the smallest blast radius
- **Team lifecycle**: `TeamCreate` at Step 2a, `TeamDelete` at Step 3b
- **All review teammates and standalone specialists are read-only** — only the lead edits files
- **Teammate idle is normal** — teammates go idle after each turn; do not treat idle notifications as errors
- **Deduplication vs. arbitration** — syntactic duplicates collapse in Step 3c; semantic conflicts (different edits on the same `file:line`) route to Step 3d
- **Preserve behavior** — fixes must not change functionality, only improve quality
- **Be surgical** — only modify code that was part of the original diff, do not refactor unrelated code
