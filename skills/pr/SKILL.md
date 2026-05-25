---
name: pr
description: Publish a pull request with automated type detection, Linear/Jira linking, PR templates, and Slack review message.
argument-hint: "[type] [ISSUE-ID]"
---

# Publish PR

!IMPORTANT: Follow this process, no matter what. Do not deviate from it.

Publish a pull request by following this automated workflow.

**Arguments:** `$0` = `[type] [ISSUE-ID]` (both optional)
- `/pr` — auto-detect type, no issue
- `/pr fix` — fix PR, no issue
- `/pr fix ENG-1234` — fix PR with a Linear issue
- `/pr fix MITB-565` — fix PR with a Jira issue
- `/pr ENG-1234` — auto-detect type with an issue ID (`[A-Z]+-\d+` matches both Linear and Jira; tracker is resolved in Step 1.6)

## 1. Review the Full Diff

### For mk-copilot project:
```bash
git --no-pager diff develop   # Inspect everything that changed vs. develop
```

### For all other projects:
First ensure you're in the right directory:
```bash
pwd
```

If not in the project directory:
```bash
cd <project-directory>
```

Then inspect the diff:
```bash
git --no-pager diff master   # Inspect everything that changed vs. master
```

or

```bash
git --no-pager diff main     # Inspect everything that changed vs. main
```

*If anything looks off, pause and ask for confirmation. Use AskUserQuestion tool to ask the user for confirmation.*

## 1.5. Determine PR Type (MANDATORY if not provided)

**Skip this step only if:**
- PR type was explicitly provided via `/pr [type]` argument.
- You are confident in the type based on the diff.

**Analysis Approach:**
- Examine file paths changed (e.g., `*.test.*`, `docs/`, configuration files)
- Analyze the diff content for patterns (new features, bug fixes, refactoring, etc.)
- Review the scope and scale of changes
- Check for conventional commit indicators in changes

**Type Detection Rules:**
- **feature** (feat): New functionality, new files/directories, significant additions to existing files
- **fix**: Bug fixes, error handling, small focused changes addressing issues
- **chore**: Dependency updates, config changes, build files, maintenance tasks
- **refactor**: Code restructuring, reorganization without changing behavior
- **docs**: Documentation, README, or content-only changes
- **test**: Test file additions or modifications
- **perf**: Performance optimizations
- **style**: Formatting, linting, or style-only changes

**Mandatory Action Items:**
1. Analyze the diff output from Step 1
2. Identify which files changed and what type of changes they represent
3. Determine the most likely PR type based on rules above
4. **Present your analysis:** "Based on the diff, I determined this is a **[TYPE]** PR because [specific reason from the changes]"
5. **Ask for confirmation if confidence < 100%:** "Does this look correct, or would you prefer **[alternative type]**?"
6. Use AskUserQuestion tool to ask the user for confirmation before proceeding to Step 2

## 1.6. Issue Tracker Detection (Optional)

Detect an issue ID (Linear or Jira) to include in branch name, PR title, and PR body. IDs from both trackers share the `[A-Z]+-\d+` shape, so the tracker is resolved after the ID is found.

**Detection Order (find the ID):**
1. Check if an ID was passed as argument (pattern: `[A-Z]+-\d+`)
2. Search conversation context for issue references
3. Check current branch name: `git rev-parse --abbrev-ref HEAD | grep -oE '[A-Z]+-[0-9]+'`
4. Check recent commits: `git log --oneline -5 | grep -oE '[A-Z]+-[0-9]+' | head -1`

**Resolve the tracker (if an ID was found):**

Try Linear first, fall back to Jira:

```bash
if linear issue view <ID> >/dev/null 2>&1; then
  TRACKER=Linear
  ISSUE_URL=$(linear issue url <ID>)
else
  TRACKER=Jira
  ISSUE_URL="https://hgdata.atlassian.net/browse/<ID>"
fi
```

- Store `ID`, `TRACKER`, and `ISSUE_URL` for use in branch naming (Step 2), PR title (Step 5), and PR body (Step 5).
- Confirm: "Detected **<TRACKER>** issue: **<ID>** — <ISSUE_URL>"

Requires the `linear` CLI on PATH (provided by the `linear-cli` skill). If `linear` is unavailable, treat the ID as Jira.

**If no ID found:**
- Continue without an issue reference (it's optional)
- Note: "No issue ID detected — proceeding without tracker reference"

## 2. Ensure on a Dedicated Branch

```bash
git rev-parse --abbrev-ref HEAD
```

- If already on a suitable branch, continue.
- Otherwise create one:

```bash
git checkout -b <branch-name>
```

**Branch naming format:**
- **With issue ID:** `{type}/{ID}-{description}` → `feat/ENG-1234-add-auth` or `feat/MITB-565-add-auth`
- **Without issue ID:** `{type}/{description}` → `feat/add-auth`

## 3. Stage and Commit All Pending Changes

```bash
git add .
git commit -m "<concise-imperative-summary (≤ 50 chars)>"
```
!IMPORTANT: NEVER commit changes to the `main`, `master`, or `develop` branch. Always create a new branch and commit your changes to that branch.

## 4. Push the Branch

```bash
git push -u origin HEAD
```

## 5. Open a Pull Request

**Configuration:**
- **Base branch:** `develop` for **mk-copilot** projects, `master` for all other repos
- **PR title format:**
  - **With issue ID:** `{type}({ID}): description` → `feat(ENG-1234): add user auth` or `feat(MITB-565): add user auth`
  - **Without issue ID:** `{type}: description` → `feat: add user auth`
- **PR body:** Use the appropriate template below based on the PR type

### Fix PR Template (type = "fix"):
```markdown
### Issue Description

<what the user experienced>

### Root Cause

<why it happened>

### Screenshots

<before / after>

### Related Issues

<linked issues or #numbers>

**{TRACKER} issue**: {ISSUE_URL}  <!-- Include only if an issue ID was detected in Step 1.6. {TRACKER} is "Linear" or "Jira". -->
```

### Feature PR Template (type = "feature" or "feat"):
```markdown
### Feature Description

<what the feature does and why>

### Screenshots

<UI shots, API examples or GIFs>

**{TRACKER} issue**: {ISSUE_URL}  <!-- Include only if an issue ID was detected in Step 1.6. {TRACKER} is "Linear" or "Jira". -->
```

### Chore PR Template (type = "chore"):
```markdown
### Description

<brief description of maintenance work or updates>

### Details

<what was updated and why>

### Related Dependencies

<any related updates or breaking changes>

**{TRACKER} issue**: {ISSUE_URL}  <!-- Include only if an issue ID was detected in Step 1.6. {TRACKER} is "Linear" or "Jira". -->
```

### Refactor PR Template (type = "refactor"):
```markdown
### Overview

<summary of code structure improvements>

### Changes

<what was reorganized or restructured>

### Impact

<any performance or maintainability improvements>

### Testing

<confirm no behavior changes>

**{TRACKER} issue**: {ISSUE_URL}  <!-- Include only if an issue ID was detected in Step 1.6. {TRACKER} is "Linear" or "Jira". -->
```

### Docs PR Template (type = "docs"):
```markdown
### Documentation Updated

<which docs were updated>

### Changes

<summary of content changes>

### Reason

<why these docs needed updating>

**{TRACKER} issue**: {ISSUE_URL}  <!-- Include only if an issue ID was detected in Step 1.6. {TRACKER} is "Linear" or "Jira". -->
```

### Test PR Template (type = "test"):
```markdown
### Test Coverage Added

<description of tests added>

### Coverage Improvement

<what scenarios are now tested>

### Related Code

<link to the code being tested>

**{TRACKER} issue**: {ISSUE_URL}  <!-- Include only if an issue ID was detected in Step 1.6. {TRACKER} is "Linear" or "Jira". -->
```

### Performance PR Template (type = "perf"):
```markdown
### Performance Improvement

<what was optimized>

### Metrics

<performance gains (before/after benchmarks)>

### Changes

<technical details of optimization>

### Impact

<affected components or users>

**{TRACKER} issue**: {ISSUE_URL}  <!-- Include only if an issue ID was detected in Step 1.6. {TRACKER} is "Linear" or "Jira". -->
```

### Style PR Template (type = "style"):
```markdown
### Style Updates

<what was changed (formatting, linting, etc.)>

### Tool/Config

<which linting or formatting tool was applied>

### Scope

<which files were affected>

**{TRACKER} issue**: {ISSUE_URL}  <!-- Include only if an issue ID was detected in Step 1.6. {TRACKER} is "Linear" or "Jira". -->
```

## 6. Request Review on Slack (MANDATORY)

Generate a brief, friendly message that includes the PR link using the template below based on the PR type:

**Message Templates by Type:**

| PR Type | Template |
|---------|----------|
| **fix** | :wrench: Fixed **[issue summary]** — would appreciate a review: [PR-URL] |
| **feature** | :rocket: New feature: **[feature name]** ready for review! [PR-URL] |
| **chore** | :broom: Maintenance update: **[what was updated]** needs review: [PR-URL] |
| **refactor** | :recycle: Code refactor for **[area/component]** — feedback welcome: [PR-URL] |
| **docs** | :books: Documentation updated: **[what changed]** [PR-URL] |
| **test** | :test_tube: Added test coverage for **[feature/area]**: [PR-URL] |
| **perf** | :zap: Performance improvement in **[area]** ready for review: [PR-URL] |
| **style** | :art: Code style/formatting updates applied: [PR-URL] |

**Action:**
1. Select the appropriate template based on the PR type from the table
2. Fill in the bracketed sections with actual details from the PR
3. **Output the complete Slack message** for the user to copy and paste into Slack

## Execution Notes

**Critical Rules:**
- Execute each step sequentially in order (1 → 1.5 → 1.6 → 2 → 3 → 4 → 5 → 6)
- **Do not skip Step 1.5** unless PR type was explicitly provided via arguments
- **Step 1.6 is optional** — proceed without a tracker reference if no ID is detected
- **Do not skip Step 6** — Slack message is mandatory before considering PR complete
- Wait for user confirmation before proceeding if any diff looks unexpected

**Type Argument Behavior:**
- **If PR type ($0) is provided:** Skip Step 1.5 and use the provided type directly
- **If PR type is NOT provided:** Unless you are confident in the type, complete PR type analysis with user confirmation at Step 1.5 before proceeding

**Standard Workflow:**
1. Execute Step 1 (diff review)
2. **MANDATORY:** Complete Step 1.5 (type detection & confirmation) — unless type was provided as argument or you are confident in the type
3. Execute Step 1.6 (issue tracker detection — Linear or Jira) — optional, use if found
4. Execute Steps 2-5 (branch, commit, push, create PR)
5. **MANDATORY:** Complete Step 6 (generate and output Slack message)
6. Confirm PR is ready: all steps completed, Slack message generated

**Optional Arguments:** `/pr [type] [ISSUE-ID]`
- `/pr` — Auto-detect PR type, no issue
- `/pr feature` — Create feature PR, no issue
- `/pr fix` — Create fix PR, no issue
- `/pr fix ENG-1234` — Create fix PR with a Linear ID
- `/pr fix MITB-565` — Create fix PR with a Jira ID
- `/pr ENG-1234` — Auto-detect type with an issue ID (tracker resolved in Step 1.6)

