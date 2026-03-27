---
name: qa
description: >-
  Generate a GitHub issue with manual QA test scenarios from code changes.
  Focuses on scenarios requiring manual verification, excluding what's
  automatable via unit/integration tests.
  Accepts a commit hash (diff to HEAD), number of commits ("last N" or bare number),
  or PR number (#123). Creates a structured checklist grouped by feature area with
  steps, expected results, and edge cases.
  This skill should be used when asked to create QA plans, test checklists, or
  manual test cases for code changes.
argument-hint: "[commit-hash | N | last N | #PR-number]"
---

# QA Test Plan Generator

!IMPORTANT: Follow this process exactly. Do not skip steps.

## Step 0: Parse Input

Inspect `$ARGUMENTS` to determine the mode:

| Pattern | Detection | Mode |
|---------|-----------|------|
| 40-char hex or short hash | Matches `/^[0-9a-f]{7,40}$/` | **commit** — diff from hash to HEAD |
| `#N` or bare number with valid PR | `gh pr view N` succeeds | **pr** — PR commit range |
| Bare number or `last N` | Matches `/^(last\s+)?\d+$/i` | **count** — last N commits |
| Empty | No argument | **count** with N=1 (last commit) |

**Disambiguation for bare numbers:** Try `gh pr view N --json number 2>/dev/null` first. If it returns a valid PR, use **pr** mode. Otherwise, treat as "last N commits."

## Step 1: Verify GitHub Remote

```bash
gh repo view --json nameWithOwner --jq '.nameWithOwner'
```

If this fails, abort: "No GitHub remote detected. `/qa` requires a GitHub repository."

## Step 2: Extract Diff and Commit Log

Based on mode:

### Commit mode
```bash
git log --oneline $HASH..HEAD
git diff --name-only $HASH..HEAD
git diff $HASH..HEAD
```

### Count mode
```bash
git log --oneline -$N
git diff --name-only HEAD~$N..HEAD
git diff HEAD~$N..HEAD
```

### PR mode
```bash
gh pr view $PR_NUMBER --json title,url,baseRefName,headRefName,number
gh pr diff $PR_NUMBER
```

Store the commit log, changed file list, and full diff for the next steps.

## Step 3: Explore Codebase

Spawn **2 parallel Explore agents** (Agent tool with `subagent_type: "Explore"`) to build contextual understanding beyond the raw diff:

### Agent 1: `change-analyzer`
Prompt: Read each changed file in full (not just diff hunks). For each file identify:
- What feature area it belongs to (auth, payments, API, UI, etc.)
- What user-facing behaviors changed
- What API endpoints or routes were modified
- What database/state changes occur
- What the happy-path flow looks like for the change

### Agent 2: `dependency-tracer`
Prompt: For each changed file, trace callers and consumers using Grep and Read. Identify:
- Which UI screens, components, or flows consume the changed code
- What existing tests cover the changed code (unit, integration, e2e) and what testing patterns/frameworks the project uses
- What config changes, new env vars, or migrations are in the diff
- What new dependencies were added (package.json, requirements.txt, etc.)
- What feature flags or permission changes are present

Provide both agents with the changed file list and commit log from Step 2.

## Step 4: Generate QA Plan

Synthesize the exploration findings into a structured QA plan. This plan targets **manual-only scenarios** — things that require human eyes, real environments, or multi-step user interaction to verify.

**Exclusion filter — do NOT include scenarios that are:**
- Pure logic/computation (unit-testable)
- Input validation & boundary values for individual fields (unit-testable)
- Individual API endpoint request/response correctness (integration-testable)
- Database CRUD correctness (integration-testable)
- Error handling for specific error codes/messages (unit-testable)
- Permission checks on individual endpoints (integration-testable)

If the dependency-tracer found existing automated test coverage for a behavior, exclude it.

**Grouping:** Cluster changes by feature area. Derive areas from directory structure, component/module boundaries, API route groups, or file naming patterns.

**For each feature area, generate scenarios in these categories:**
1. **User flows & interactions** — multi-step workflows, navigation paths, form submission sequences spanning multiple components/pages
2. **Visual & layout** — UI rendering, responsive behavior, content overflow, visual regressions, animation/transition correctness
3. **Cross-system integration** — behavior across service boundaries, third-party integrations, webhook flows, real external API behavior
4. **State & data consistency** — race conditions, concurrent user actions, stale data, cache invalidation, optimistic update rollbacks
5. **Environment-specific behavior** — browser/device differences, network conditions (slow/offline), timezone/locale effects, feature flag combinations

Only include categories relevant to the changes — omit empty categories.

**Additionally generate:**
- **Prerequisites** — inferred from config changes: env vars, migrations, feature flags, required access/roles, test data setup
- **Regression checks** — user-visible regressions only (not internal correctness already covered by automated tests)
- **Error handling** — graceful degradation visible to the user (not API error codes or programmatic error responses)

## Step 5: Create GitHub Issue

First ensure the `qa` label exists:
```bash
gh label create qa --description "Manual QA test plan" --color "0E8A16" 2>/dev/null || true
```

Then create the issue using this template structure. Use HEREDOC with single-quoted delimiter to prevent shell interpolation:

```bash
gh issue create \
  --title "QA: [concise feature summary]" \
  --label "qa" \
  --body "$(cat <<'EOF'
## QA Test Plan

**Source:** [commit range or PR reference]
**Generated:** [today's date]
**Related PR:** #N  <!-- include only if PR mode -->

---

### Prerequisites

> Complete before starting QA.

- [ ] [prerequisite 1]
- [ ] [prerequisite 2]

---

### 1. [Feature Area Name]

#### 1.1 [Scenario Title]
**Preconditions:** [state/setup needed]

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | [action] | [expected] |
| 2 | [action] | [expected] |

- [ ] Verified

**Edge cases:**
- [ ] [boundary / negative / error scenario]
- [ ] [another edge case]

#### 1.2 [Next Scenario]
...

---

### 2. [Next Feature Area]
...

---

### Regression Checks

> Existing behavior that must remain unchanged.

- [ ] [regression scenario 1]
- [ ] [regression scenario 2]

---

### Error Handling

- [ ] [error state 1 — expected graceful behavior]
- [ ] [error state 2 — expected graceful behavior]

---

<sub>Generated by /qa from [input description]</sub>
EOF
)"
```

**PR linking:** If input was a PR number, include `**Related PR:** #N` in the body. If not PR mode, omit that line.

## Step 6: Confirm

Display the created issue URL and a brief summary:

```
QA issue created: [URL]
- [N] feature areas
- [N] test scenarios
- [N] edge cases
```

## Execution Notes

- **Large diffs (>50KB):** Pass only the changed file list to explore agents and instruct them to read files directly instead of embedding the full diff.
- **PR from fork:** If `gh pr diff` fails, fall back to `git diff origin/$BASE...origin/$HEAD`.
- **No prerequisites detected:** Omit the Prerequisites section rather than leaving it empty.
- **Single small change:** Still group under a feature area — even one scenario should follow the template for consistency.
