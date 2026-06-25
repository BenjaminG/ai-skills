---
name: qa-plan
description: >-
  Draft a manual QA test plan for a pull request, tailored for a PM or QA
  tester (not a developer). Auto-detects the current PR from the branch, or
  takes a PR number/URL. Produces steps that can be run with only a browser
  and the app's admin UI — no terminal, SQL, GraphQL, or code access.
  Always renders in chat for review and iteration first; publishes to a
  markdown file, GitHub issue, or Linear sub-issue only on explicit approval.
  Companion skill `qa-run` (future) will guide the tester through executing
  the plan.
  This skill should be used when asked to create a QA plan, test checklist,
  or manual test cases for a PR.
argument-hint: "[pr-number-or-url] [--file | --github | --linear]"
---

# QA Plan Drafter

!IMPORTANT: Draft and iterate in chat. Publish only after explicit user approval.

## Step 0: Resolve the PR

Parse `$ARGUMENTS`. First, strip any trailing publish flag (`--file`, `--github`, `--linear`) into `PUBLISH_TARGET` (default: unset — draft only). The remainder, if any, is the PR reference.

- **PR ref given** (number or URL) → use it directly.
- **No PR ref** → detect from current branch:
  ```bash
  gh pr list --head "$(git branch --show-current)" --state open --json number,url,title,headRefName,baseRefName --limit 5
  ```
  - Exactly one result → use it.
  - Zero results → abort: "No open PR found for branch. Pass a PR number (e.g. `/qa-plan 12363`)."
  - More than one → list them and ask the user which to use.

Echo the resolved PR as `#<n> — <title> — <url>` so the user can confirm.

## Step 1: Validate publish target (if set)

| Flag | `PUBLISH_TARGET` | Precondition |
|------|------------------|--------------|
| (none) | unset | none — draft only, stays in chat |
| `--file` | `file` | none |
| `--github` | `github` | `gh repo view --json nameWithOwner` succeeds |
| `--linear` | `linear` | `linear` CLI installed **and** a ticket key discoverable from the PR (see Step 6) |

Validate the precondition now. If it fails, abort before doing any work.

## Step 2: Fetch PR diff

```bash
gh pr view $PR_NUMBER --json title,url,body,baseRefName,headRefName,number
gh pr diff $PR_NUMBER
```

If `gh pr diff` fails (fork PR), fall back to `git diff origin/$BASE...origin/$HEAD`.

Store the title, body, changed files, and diff.

## Step 2.5: Fetch Linear context (best-effort)

The PR diff shows *what changed in code*; the Linear issue says *what the feature should do* — acceptance criteria, the validated product rule, any scope/matrix table. Pull it in to frame scenarios against intended behavior.

1. Derive the key (same logic as Step 6's `linear` publish):
   - Regex `[A-Z]+-\d+` against the branch name (e.g. `feat/BOF-218-foo` → `BOF-218`).
   - If no match, grep the PR body for a Linear URL or `[A-Z]+-\d+`.
   - Store the result as `LINEAR_KEY` (reused in Step 6).
2. If a key is found:
   ```bash
   linear issue view "$LINEAR_KEY" --json
   ```
   Read the description, acceptance criteria, product rule, and any scope table.
3. **Best-effort:** if no key is found, or `linear` is missing / auth fails, note "no Linear context" and continue. This is enrichment, not a precondition — a PR with no ticket still produces a plan. (Only `--linear` *publishing* hard-requires the key, validated in Step 1.)
4. Derive the **task slug** used to group artifacts on disk: `TASK = LINEAR_KEY` if known, else `pr-<PR_NUMBER>` (e.g. `BOF-218` or `pr-12363`). The `file` target (Step 6) writes under `tasks/<TASK>/`.

## Step 3: Explore codebase

Spawn **2 parallel Explore agents** (Agent tool, `subagent_type: "Explore"`).

### Agent 1: `change-analyzer`
For each changed file, read it in full and identify:
- Feature area (auth, payments, UI, etc.)
- User-facing behaviors that changed
- Routes / screens / pages affected
- Which state transitions or side effects are new
- How the changes map to the Linear acceptance criteria / product rule (from Step 2.5, if available)

### Agent 2: `tester-surface-scout`
Map out the **tester-facing surfaces** needed to exercise these changes without dev tooling:
- Back-office / admin UI routes that let a non-dev configure test data (e.g. `/tools/console` style pages, feature-flag toggles in the UI, entity editors, date fields on entities)
- Email sandbox (e.g. Mailpit) URL in ephemeral/preview envs
- Ephemeral env URL pattern for this repo (e.g. `*-pr-<N>.*`)
- Manual job/cron triggers exposed in the admin UI
- Existing automated test coverage (unit/integration/e2e) for the changed code — so those paths can be excluded from the QA plan

Give both agents the changed file list and PR body.

## Step 4: Draft the plan (PM/QA-executable)

Synthesize findings into a plan a PM or QA can run **with only a browser + the app's admin UI + the email sandbox**.

### Hard exclusion — drop any step that requires:

- Reading source code, running scripts, or opening a terminal
- Direct database edits (Mongo shell, psql, Atlas UI writes, raw query panels)
- GraphQL playground, `curl`, Postman, or browser devtools beyond normal use
- **Modifying the system clock** or waiting for a real elapsed duration that blocks a QA session (> ~1h). *Seeding a dated fixture through the BO (e.g. setting a `startDate` J+32 on a quote) is fine — the `tester-surface-scout` should have flagged that path.*
- Simulating SMTP/infra failures at the protocol level
- Modifying env vars, editing feature-flag configs outside the UI, or redeploying

If a critical scenario can only be verified via one of the above, move it to **"Out of scope — covered by automated tests"** (don't delete, so the dev confirms coverage).

### Also exclude (already covered by tests):

- Pure logic / input validation / boundary values
- Individual endpoint request/response correctness
- DB CRUD correctness
- Error code / message strings
- Per-endpoint permission checks

If the `tester-surface-scout` found automated coverage, exclude it.

### For each scenario

Require a **"How to reach this state"** line that names the concrete tester-facing surface (BO route, screen path, Mailpit inbox, env URL). No surface → out of scope.

Ground each scenario's expected results in the Linear acceptance criteria (Step 2.5) when available — test the *intended* behavior, not just the behavior observed in the diff.

**Group by feature area.** Within each area, include only the relevant categories:
1. User flows & interactions (multi-step)
2. Visual & layout
3. Cross-system integration (user-observable)
4. State & data consistency (user-observable)
5. Environment-specific behavior (browser, locale, FF combinations reachable from UI)

Also produce:
- **Prerequisites** — only what the tester must have **before clicking Step 1** (env URL, credentials, test-user account, label assignment). Not what the dev did to prepare the branch, not setup that belongs inside a scenario's "How to reach this state". Aim for ≤ 5 items.
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

> What the tester needs before starting. Keep to ≤ 5 items.

- [ ] Access to the ephemeral env: <url>
- [ ] Back-office account with role: <role>
- [ ] Mailpit inbox: <url>

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

## Step 5: Draft & iterate (always — terminal preview)

Render the plan in chat (fenced markdown). Then ask:

> Review the plan. Reply with edits, or `publish` to send it to **<PUBLISH_TARGET>** (or pick a target: `file`, `github`, `linear`).

Apply user edits and re-render until the user says `publish` (or equivalent: "ship it", "go", "ok publish"). Never proceed to Step 6 without explicit approval.

If `PUBLISH_TARGET` is unset and the user never asks to publish, stop here — the draft lives in the chat.

## Step 6: Publish (only after approval)

**Always write the approved plan body to a temp file first**, then pass `--body-file` / `--description-file`. This avoids HEREDOC breakage on plans containing backticks, `$`, `|`, or nested code fences.

```bash
TMP=$(mktemp -t qa-plan.XXXXXX.md)
# Write the approved plan body to $TMP via the Write tool
```

### `file`
Write to `tasks/<TASK>/qa-plan.md` via the Write tool (`TASK` from Step 2.5 — `LINEAR_KEY` or `pr-<PR_NUMBER>`). Create `tasks/<TASK>/` if it doesn't exist. (No temp file needed — this target *is* a file.) This keeps QA artifacts grouped per task instead of scattered at the repo root.

### `github`
```bash
gh label create qa --description "Manual QA test plan" --color "0E8A16" 2>/dev/null || true
gh issue create \
  --title "QA: <PR title>" \
  --label "qa" \
  --body-file "$TMP"
rm -f "$TMP"
```

### `linear`
1. Use `LINEAR_KEY` from Step 2.5. If it's unset (no key in branch name or PR body), abort: "No Linear ticket key found in branch name or PR body. Pass one explicitly or re-run with `--github`."
2. Create the sub-issue (no label — see below):
   ```bash
   linear issue create \
     --parent "$LINEAR_KEY" \
     --title "QA: <PR title>" \
     --description-file "$TMP"
   rm -f "$TMP"
   ```
3. **Do not apply a QA label automatically.** Label names vary per team and often trigger Slack notifications (e.g. `QA` vs `QA Produit`). After creation, print:
   > Sub-issue created: <URL>
   > To notify the QA channel, apply your team's QA label manually (e.g. `linear issue update <KEY> --label "QA Produit"`).

## Step 7: Confirm

- No publish: "QA plan drafted above — N feature areas, M scenarios. Reply `publish` with a target to send it."
- `file`: "QA plan written to tasks/<TASK>/qa-plan.md."
- `github`: "QA issue created: <URL>."
- `linear`: "Linear sub-issue created: <URL>. Apply the QA label manually to notify the channel."

## Execution notes

- **Iteration is the default.** Publishing without the user saying `publish` is a bug.
- **Large diffs (> 50KB):** pass only the changed file list to the Explore agents; let them read files directly.
- **PR body as signal:** the PR body often lists what the author already tested — use it to skip redundant scenarios.
- **Companion:** a future `qa-run` skill will pick up a plan produced here and walk the tester through execution.

## Audience & dogfooding

The plan targets a non-developer tester. The dev (you) runs the plan first
locally as a dogfooding pass — same constraints as the PM. If a step can't
be executed via BO + browser + Mailpit, the plan is wrong (or the BO is
missing a surface) — fix it before handoff, don't break the audience rule.
