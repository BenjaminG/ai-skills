---
name: qa-run
description: >-
  Execute a qa-plan.md interactively. Walks through each scenario with the
  user, logs status + findings + notes to a sibling qa-results.md
  (append-only). Supports resume — re-running picks up at the first
  unchecked or failed case. Same audience constraints as the plan: browser
  + admin UI + email sandbox only. No terminal, no DB, no GraphQL — even
  when the runner is the dev.
  This skill should be used to run a manual QA pass against a plan
  produced by /qa-plan, whether the runner is the dev (dogfooding before
  handoff) or the PM/QA tester.
argument-hint: "[plan-path]"
---

# QA Run

!IMPORTANT: Stay within the plan's audience constraints. If a step needs
a terminal, DB shell, or GraphQL playground to verify, don't run it that
way — log it as a plan-defect finding instead.

## Step 0: Locate the plan

Resolve the plan file:
- Arg given → use it.
- No arg → most recent `./qa-plan-*.md` by mtime. None found → abort.

Derive the results path from the plan path: `qa-plan-X.md` → `qa-results-X.md` in the same directory.

## Step 1: Initialize or resume

If `qa-results-X.md` does not exist:
- Create it from the template below.
- Pre-populate § Status with one `[ ]` line per scenario (parsed from plan headings `### N.M`).
- Start at §1.1.

If it exists:
- Read it.
- Find the first scenario whose status is `[ ]` or `[!]`.
- Echo: `Resuming at §X.Y — <title>. <K> passed, <M> failed, <P> pending.`

## Step 2: Iterate scenarios

For each scenario in plan order (skip `[x]`, retry `[ ]` and `[!]`):

1. **Announce**: §X.Y title, "How to reach this state", preconditions.
2. **Run together**: present the steps from the plan's table. The user performs them in the browser/BO/Mailpit, or asks Claude to drive via CDP (same actions a human would do — no shortcuts via JS console, GraphQL, or DB).
3. **Decide outcome and append to results**:
   - Pass → `[x] §X.Y — passed (<short note if useful>)`
   - Fail → `[!] §X.Y — failed → Finding #<n>` + new Finding entry
   - Skip → `[~] §X.Y — skipped (<reason>)` + Finding tagged `plan-defect` if the plan itself is the problem
4. If a gotcha or recipe surfaced, append a one-liner to § Notes.
5. Write immediately. Don't batch.

## Step 3: End-of-run summary

- Totals: passed / failed / skipped / pending.
- Triage table grouped by severity: `blocker`, `improvement`, `nit`, `plan-defect`.
- Suggest next step based on what's open:
  - Blockers → fix via `/ralph-tui`, then re-run `/qa-run` on the same results file.
  - Plan defects → update via `/qa-plan` (or hand-edit), then re-run.
  - Nits only → ready to flip the PR to ready-for-review.

## qa-results.md template

```markdown
# QA Results — <plan title>

**Plan:** ./qa-plan-<X>.md
**Started:** <date>
**Last run:** <date>

## Status
- [ ] §1.1 — <title>
- [ ] §1.2 — <title>
- [ ] §2.1 — <title>

## Findings

### #1 <title> — <blocker|improvement|nit|plan-defect>
**Scenario:** §X.Y
**Repro:** <steps observed>
**Expected:** <from plan>
**Observed:** <what happened>
**Notes:** <suspected cause / scope>

## Notes
- <gotcha or recipe>
```

## Rules

- **Plan is immutable.** Never edit `qa-plan-X.md`. If the plan is wrong, log a `plan-defect` finding and tell the user to fix it separately.
- **Status lines are one line.** Detail goes in Findings.
- **Append-only.** Never rewrite earlier entries. To retry a failed case, the user flips `[!]` to `[ ]` manually, or asks Claude to retry a specific scenario.
- **Browser CDP is OK** for clicking faster than a human, not for bypassing audience constraints. No `evaluate()` shortcuts to read Mongo, no GraphQL fetches, no `localStorage` poking beyond what a normal user does.
- **One scenario at a time.** Don't pre-execute and dump all results — each step needs human verification before moving on.
