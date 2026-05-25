---
name: qa-run
description: >-
  Execute a qa-plan interactively. The plan can live locally (qa-plan-X.md)
  or remotely on Linear (sub-issue created by /qa-plan --linear). Walks
  through each scenario with the user, logs status + findings + notes to a
  sibling qa-results.md (append-only, source of truth). When the source is
  Linear, mirrors findings and the final summary as comments on the
  sub-issue. Supports resume — re-running picks up at the first unchecked
  or failed case. Same audience constraints as the plan: browser + admin
  UI + email sandbox only. No terminal, no DB, no GraphQL — even when the
  runner is the dev.
  This skill should be used to run a manual QA pass against a plan
  produced by /qa-plan, whether the runner is the dev (dogfooding before
  handoff) or the PM/QA tester.
argument-hint: "[plan-path | linear-key | linear-url]"
---

# QA Run

!IMPORTANT: Stay within the plan's audience constraints. If a step needs
a terminal, DB shell, or GraphQL playground to verify, don't run it that
way — log it as a plan-defect finding instead.

## Step 0: Locate the plan

The argument may be a local path, a Linear issue key, or a Linear URL.
Classify it before resolving:

- Matches `^[A-Z]+-\d+$` → **Linear key** (e.g. `BOF-218`).
- Contains `linear.app/` → **Linear URL** (extract the key from the path).
- Anything else → **local path**.
- No arg → local fallback: most recent `./qa-plan-*.md` by mtime. None found → abort.

### Local path
Use the file directly. Derive results path: `qa-plan-X.md` → `qa-results-X.md` in the same directory. `SOURCE=local`.

### Linear key or URL
1. Use the **`linear-cli`** skill to fetch the issue's title and description body. Do not inline CLI flags here — let `linear-cli` handle the mechanics.
2. If the issue title does **not** start with `QA:` it's likely the parent ticket, not the QA sub-issue. Ask `linear-cli` to list sub-issues and pick the one whose title starts with `QA:`.
   - Zero matches → abort: "No `QA: ...` sub-issue found under <KEY>. Run `/qa-plan --linear` first or pass the sub-issue key directly."
   - Multiple matches → list them and ask the user which to use.
3. Persist the description body to `./qa-plan-<SUBISSUE_KEY>.md`. If the file already exists with different content, ask before overwriting (the user may have local edits).
4. Derive results path: `./qa-results-<SUBISSUE_KEY>.md`. Set `SOURCE=linear` and remember `SUBISSUE_KEY` for Step 2/3 mirroring.

## Step 1: Initialize or resume

If `qa-results-X.md` does not exist:
- **If `SOURCE=linear`**, first ask `linear-cli` to list comments on the sub-issue and check whether any start with the `<!-- qa-run -->` marker (signature for runs already mirrored to Linear). If yes, warn the user: "Linear already has qa-run comments from a previous run, but no local results file exists. Reply `fresh` to start over, or point to an existing `qa-results-*.md` to resume from." Wait for the answer before proceeding.
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
2. **Run together**: present the steps from the plan's table. The user performs them in the browser/BO/Mailpit, or asks Claude to drive via /autobrowse skill (same actions a human would do — no shortcuts via JS console, GraphQL, or DB).
3. **Decide outcome and append to results**:
   - Pass → `[x] §X.Y — passed (<short note if useful>)`
   - Fail → `[!] §X.Y — failed → Finding #<n>` + new Finding entry
   - Skip → `[~] §X.Y — skipped (<reason>)` + Finding tagged `plan-defect` if the plan itself is the problem
4. If a gotcha or recipe surfaced, append a one-liner to § Notes.
5. Write immediately. Don't batch.
6. **Mirror to Linear (only if `SOURCE=linear` and outcome is Fail or Skip-as-plan-defect):** delegate to `linear-cli` to add a comment on `SUBISSUE_KEY` whose body is the new Finding entry, prefixed with `<!-- qa-run -->` on the first line so future runs can detect it. If the comment fails (auth, network), print the error and continue — local results stay the source of truth.

## Step 3: End-of-run summary

- Totals: passed / failed / skipped / pending.
- Triage table grouped by severity: `blocker`, `improvement`, `nit`, `plan-defect`.
- Suggest next step based on what's open:
  - Blockers → fix via `/ralph-tui`, then re-run `/qa-run` on the same results file.
  - Plan defects → update via `/qa-plan` (or hand-edit), then re-run.
  - Nits only → ready to flip the PR to ready-for-review.

**Mirror to Linear (only if `SOURCE=linear`):** delegate to `linear-cli` to post the same summary as a single comment on `SUBISSUE_KEY`, with `<!-- qa-run -->` on the first line. Comment failures don't block — the local results file is the canonical record.

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

- **Plan is immutable.** Never edit `qa-plan-X.md`, and never edit the Linear sub-issue's description either. If the plan is wrong, log a `plan-defect` finding and tell the user to fix it separately (re-run `/qa-plan` for Linear plans).
- **Local results are the source of truth.** Linear comments are a mirror; if they diverge or fail to post, the local `qa-results-X.md` wins. Never re-derive state from Linear comments.
- **Status lines are one line.** Detail goes in Findings.
- **Append-only.** Never rewrite earlier entries. To retry a failed case, the user flips `[!]` to `[ ]` manually, or asks Claude to retry a specific scenario.
- **Browser CDP is OK** for clicking faster than a human, not for bypassing audience constraints. No `evaluate()` shortcuts to read Mongo, no GraphQL fetches, no `localStorage` poking beyond what a normal user does unless the user doing the explicitly allows it to verify a tricky state.
- **One scenario at a time.** Don't pre-execute and dump all results — each step needs human verification before moving on.
