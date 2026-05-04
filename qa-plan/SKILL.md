---
name: qa-plan
description: >-
  Draft a manual QA test plan for a pull request, tailored for a PM or QA
  tester (not a developer). Auto-detects the current PR from the branch, or
  takes a PR number/URL. Produces steps that can be run with only a browser
  and the app's admin UI — no terminal, SQL, GraphQL, or code access.
  Always renders in chat first so the user can iterate; only publishes to
  terminal, file, GitHub issue, or Linear sub-issue on explicit approval.
  Companion skill `qa-run` (future) will guide the tester through executing
  the plan.
  This skill should be used when asked to create a QA plan, test checklist,
  or manual test cases for a PR.
argument-hint: "[pr-number-or-url] [--terminal | --file | --github | --linear]"
---

# QA Plan Drafter

!IMPORTANT: Follow this process exactly. Never publish before the user approves the draft.

## Step 0: Resolve the PR

Parse `$ARGUMENTS`. First, strip any trailing output flag (`--terminal`, `--file`, `--github`, `--linear`) into `OUTPUT_MODE` (default: `terminal`). The remainder, if any, is the PR reference.

- **PR ref given** (number or URL) → use it directly.
- **No PR ref** → detect from current branch:
  ```bash
  gh pr view --json number,url,title,headRefName,baseRefName,state
  ```
- **No PR on current branch and no arg** → abort: "No PR found. Check out the feature branch or pass a PR number (e.g. `/qa-plan 12363`)."

Echo the resolved PR as `#<n> — <title> — <url>` so the user can confirm.

## Step 1: Validate output target

| Flag | `OUTPUT_MODE` | Precondition |
|------|---------------|--------------|
| `--terminal` (or none) | `terminal` | none |
| `--file` | `file` | none |
| `--github` | `github` | `gh repo view --json nameWithOwner` must succeed |
| `--linear` | `linear` | `linear` CLI installed **and** a Linear ticket key discoverable from the PR (see Step 5) |

Validate the precondition now. If it fails, abort with a clear message before doing any work.

## Step 2: Fetch PR diff

```bash
gh pr view $PR_NUMBER --json title,url,body,baseRefName,headRefName,number
gh pr diff $PR_NUMBER
```

If `gh pr diff` fails (fork PR), fall back to `git diff origin/$BASE...origin/$HEAD`.

Store the title, body, changed files, and diff.

## Step 3: Explore codebase

Spawn **2 parallel Explore agents** (Agent tool, `subagent_type: "Explore"`).

### Agent 1: `change-analyzer`
For each changed file, read it in full and identify:
- Feature area (auth, payments, UI, etc.)
- User-facing behaviors that changed
- Routes / screens / pages affected
- Which state transitions or side effects are new

### Agent 2: `tester-surface-scout`
Map out the **tester-facing surfaces** needed to exercise these changes without dev tooling:
- Back-office / admin UI routes that let a non-dev configure test data (e.g. `/tools/console` style pages, feature-flag toggles in the UI, entity editors)
- Email sandbox (e.g. Mailpit) URL in ephemeral/preview envs
- Ephemeral env URL pattern for this repo (e.g. `*-pr-<N>.*`)
- Manual job/cron triggers exposed in the admin UI
- Existing automated test coverage (unit/integration/e2e) for the changed code — so those paths can be excluded from the QA plan

Give both agents the changed file list and PR body.

## Step 4: Draft the plan (PM/QA-executable)

Synthesize findings into a plan a PM or QA can run **with only a browser + the app's admin UI + the email sandbox**.

### Hard exclusion — drop any step that requires:

- Reading source code, running scripts, or opening a terminal
- Direct database edits (Mongo shell, psql, Atlas UI writes)
- GraphQL playground, `curl`, Postman, or browser devtools beyond normal use
- Time-travel / waiting > 24h / simulating SMTP failures / tweaking system clock
- Modifying env vars, editing feature-flag configs, or redeploying

If a critical scenario can only be verified this way, move it to the **"Out of scope — covered by automated tests"** section at the end of the plan (don't delete it, so the dev can confirm coverage exists).

### Also exclude (already covered by tests):

- Pure logic / input validation / boundary values
- Individual endpoint request/response correctness
- DB CRUD correctness
- Error code / message strings
- Per-endpoint permission checks

If the `tester-surface-scout` found automated test coverage for a behavior, exclude it.

### For each scenario

Require a **"How to reach this state"** line that names the concrete tester-facing surface (BO route, screen path, Mailpit inbox, env URL). No surface → out of scope.

**Group by feature area.** Within each area, include only the relevant categories:
1. User flows & interactions (multi-step)
2. Visual & layout
3. Cross-system integration (user-observable)
4. State & data consistency (user-observable)
5. Environment-specific behavior (browser, locale, FF combinations reachable from UI)

Also produce:
- **Prerequisites** — data fixtures / roles / feature flag states / ephemeral env URL / credentials the tester needs before starting
- **Regression checks** — user-visible only
- **Error handling** — graceful degradation visible in the UI

### Shared body template

```markdown
## QA Plan — #<PR_NUMBER> <PR_TITLE>

**PR:** <url>
**Branch:** <head> → <base>
**Generated:** <date>

---

### Prerequisites

> Complete before starting QA.

- [ ] Access to the ephemeral env: <url pattern>
- [ ] Back-office credentials with role: <role>
- [ ] Mailpit inbox: <url>
- [ ] Test data: <fixture description>

---

### 1. <Feature Area>

#### 1.1 <Scenario Title>
**How to reach this state:** <BO route / app screen / Mailpit inbox>
**Preconditions:** <state needed>

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ... | ... |
| 2 | ... | ... |

- [ ] Verified

**Edge cases:**
- [ ] <user-observable edge>

---

### Regression Checks

- [ ] <user-visible behavior that must still work>

---

### Error Handling

- [ ] <graceful UI behavior>

---

### Out of scope — covered by automated tests

> Listed so the dev can confirm coverage exists; the tester does not run these.

- <scenario> — covered by `<test file or description>`

---

<sub>Drafted by /qa-plan from PR #<N></sub>
```

## Step 5: Preview & iterate (DO NOT publish yet)

Render the plan in chat (fenced markdown). Then ask:

> Review the plan. Reply with edits, or `publish` to send it to **<OUTPUT_MODE>**.

Apply user edits and re-render until they say `publish` (or equivalent: "ship it", "go", "ok publish"). Never proceed to Step 6 without explicit approval.

## Step 6: Publish (only after approval)

### `terminal`
Already done in Step 5. Skip to Step 7.

### `file`
Write to `./qa-plan-<timestamp>.md` via the Write tool. Timestamp = `date +%Y%m%d-%H%M%S`.

### `github`
```bash
gh label create qa --description "Manual QA test plan" --color "0E8A16" 2>/dev/null || true
gh issue create \
  --title "QA: <PR title>" \
  --label "qa" \
  --body "$(cat <<'EOF'
<rendered plan body>
EOF
)"
```

### `linear`
1. Find the parent Linear ticket key:
   - Regex `[A-Z]+-\d+` against the branch name (e.g. `feat/BOF-218-foo` → `BOF-218`).
   - If no match, grep the PR body for a Linear URL or `[A-Z]+-\d+`.
   - If still nothing, abort: "No Linear ticket key found in branch name or PR body. Pass one explicitly or re-run with `--github`."
2. Create the sub-issue (no label — see below):
   ```bash
   linear issue create \
     --parent <KEY> \
     --title "QA: <PR title>" \
     --description "<rendered plan body>"
   ```
3. **Do not apply a QA label automatically.** Label names vary per team and often trigger Slack notifications (e.g. `QA` vs `QA Produit`). After the issue is created, print:
   > Sub-issue created: <URL>
   > To notify the QA channel, apply your team's QA label manually (e.g. `linear issue update <KEY> --label "QA Produit"`).

## Step 7: Confirm

- `terminal`: "QA plan rendered above — N feature areas, M scenarios."
- `file`: "QA plan written to <absolute path>."
- `github`: "QA issue created: <URL>."
- `linear`: "Linear sub-issue created: <URL>. Apply the QA label manually to notify the channel."

## Execution notes

- **Iteration is the default.** Publishing without the user saying `publish` is a bug.
- **Large diffs (> 50KB):** pass only the changed file list to the Explore agents; let them read files directly.
- **PR body as signal:** the PR body often lists what the author already tested — use it to skip redundant scenarios, and call it out in the Prerequisites.
- **Companion:** a future `qa-run` skill will pick up a plan produced here and walk the tester through execution.
