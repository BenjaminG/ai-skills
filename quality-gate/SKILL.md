---
name: quality-gate
description: Run parallel quality reviews (React, SOLID, Security, Simplification) on branch changes and auto-fix issues
argument-hint: [base-branch]
---

# Quality Gate

!IMPORTANT: Follow this process exactly. Do not skip steps.

**Arguments:** `$0` (optional) — base branch to diff against. If omitted, auto-detect.

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

## Step 2: Parallel Review (4 Agents)

Spawn review agents **in parallel** using a single message with multiple Task tool calls.

**Skip Agent 1** if the project does not use React/Next.js.

Each agent prompt MUST include:
1. The full diff from Step 1
2. The list of changed files
3. Instructions to read the relevant skill docs for review criteria
4. The output format below

### Agent 1: React/Next.js Best Practices
- **subagent_type**: `general-purpose`
- **name**: `react-reviewer`
- Instruct the agent to:
  - Read `/Users/bgelis/.agents/skills/vercel-react-best-practices/SKILL.md` and any rule files in its `rules/` subdirectory that are relevant to the diff
  - Review ONLY the changed code in the diff against the rules
  - Categorize each finding as FIX or NITPICK

### Agent 2: SOLID Principles
- **subagent_type**: `general-purpose`
- **name**: `solid-reviewer`
- Instruct the agent to:
  - Read `/Users/bgelis/.agents/skills/applying-solid-principles/SKILL.md` and its sub-documents
  - Review ONLY the changed code against SOLID principles and clean code practices
  - Categorize each finding as FIX or NITPICK

### Agent 3: Security Review
- **subagent_type**: `general-purpose`
- **name**: `security-reviewer`
- Instruct the agent to:
  - Read `/Users/bgelis/.agents/skills/security-review/SKILL.md`
  - Review ONLY the changed code against the security checklist
  - Categorize each finding as FIX or NITPICK

### Agent 4: Code Simplification
- **subagent_type**: `general-purpose`
- **name**: `simplify-reviewer`
- Instruct the agent to:
  - Read `/Users/bgelis/.agents/skills/simplify/SKILL.md`
  - Review the changed files for simplification opportunities (clarity, consistency, maintainability)
  - Categorize each finding as FIX or NITPICK

### Classification Rules (include in each agent prompt)

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

### Required Output Format (include in each agent prompt)

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

## Step 3: Consolidate Findings

After all agents complete:

1. Collect all **FIX** items across all 4 agents
2. Deduplicate overlapping findings on the same file:line
3. Display a summary:

```
### Quality Gate Results

**Fixes to auto-apply:** N items
- [React] file:line — description (x items)
- [SOLID] file:line — description (x items)
- [Security] file:line — description (x items)
- [Simplify] file:line — description (x items)

**Nitpicks for review:** N items
```

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
```

Ask: "Which nitpicks should I apply?" with options:
- All of them
- None
- Let me pick (then list individually)

## Step 6: Apply Selected Nitpicks

Apply whichever nitpicks the user selected.

## Step 7: Commit & Push (if changes made)

If any changes were applied (fixes or nitpicks):

```bash
git add .
git commit -m "refactor: apply quality gate fixes"
```

If a remote branch exists and the branch was already pushed:
```bash
git push
```

## Execution Notes

- **Total agents**: 3-4 (skip React agent if not a React project)
- **All review agents are read-only** — they report findings, the main process applies fixes
- **Deduplication matters** — multiple agents may flag the same issue differently; apply only once
- **Preserve behavior** — fixes must not change functionality, only improve quality
- **Be surgical** — only modify code that was part of the original diff, do not refactor unrelated code
