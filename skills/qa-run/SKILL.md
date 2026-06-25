---
name: qa-run
description: >-
  Execute a qa-plan interactively. The plan can live locally (qa-plan-X.md)
  or remotely on Linear (sub-issue created by /qa-plan --linear). Walks
  through each scenario with the user, logs status + findings + notes to a
  sibling qa-results.md (append-only, source of truth). When the source is
  Linear, mirrors findings and the final summary as comments on the
  sub-issue. Supports resume — re-running picks up at the first unchecked
  or failed case. Verification stays browser-only (admin UI + email sandbox);
  no terminal/DB/GraphQL is used to confirm a pass. A dev runner may read the
  source to root-cause a failure and cite file:line in the finding.
  This skill should be used to run a manual QA pass against a plan
  produced by /qa-plan, whether the runner is the dev (dogfooding before
  handoff) or the PM/QA tester.
argument-hint: "[plan-path | linear-key | linear-url]"
---

# QA Run

!IMPORTANT: **Verification is browser-only.** Confirm a scenario by what a
user observes in the browser / admin UI / email sandbox — never mark a step
passed because a DB query, GraphQL response, or log line says so. If a step
can *only* be confirmed via terminal/DB/GraphQL, that's a plan-defect: log it,
don't fake the pass.

**Root-causing is not verification.** Once a step fails or behaves oddly, a
dev runner is encouraged to read the source to explain *why* and cite
`file:line` in the Finding (see Step 2.3). That's an asset, not a violation of
the constraint above — the constraint governs how you *confirm a pass*, not how
you *explain a failure*.

## Step 0: Locate the plan

The argument may be a local path, a Linear issue key, or a Linear URL.
Classify it before resolving:

- Matches `^[A-Z]+-\d+$` → **Linear key** (e.g. `BOF-218`).
- Contains `linear.app/` → **Linear URL** (extract the key from the path).
- Anything else → **local path**.
- No arg → local fallback: most recent `tasks/*/qa-plan.md` by mtime (legacy root-level `./qa-plan-*.md` are still accepted if passed explicitly). None found → abort.

### Local path
Use the file directly. Derive results path: `qa-results.md` (or `qa-results-X.md` for legacy names) in the **same directory** as the plan — e.g. `tasks/BOF-218/qa-plan.md` → `tasks/BOF-218/qa-results.md`. `SOURCE=local`.

### Linear key or URL
1. Use the **`linear-cli`** skill to fetch the issue's title and description body. Do not inline CLI flags here — let `linear-cli` handle the mechanics.
2. If the issue title does **not** start with `QA:` it's likely the parent ticket, not the QA sub-issue. Ask `linear-cli` to list sub-issues and pick the one whose title starts with `QA:`.
   - Zero matches → abort: "No `QA: ...` sub-issue found under <KEY>. Run `/qa-plan --linear` first or pass the sub-issue key directly."
   - Multiple matches → list them and ask the user which to use.
3. Persist the description body to `tasks/<SUBISSUE_KEY>/qa-plan.md` (create `tasks/<SUBISSUE_KEY>/` if missing). If the file already exists with different content, ask before overwriting (the user may have local edits).
4. Derive results path: `tasks/<SUBISSUE_KEY>/qa-results.md`. Set `SOURCE=linear` and remember `SUBISSUE_KEY` for Step 2/3 mirroring.

## Step 1: Initialize or resume

If the results file (`tasks/<TASK>/qa-results.md`) does not exist:
- **If `SOURCE=linear`**, first ask `linear-cli` to list comments on the sub-issue and check whether any look like a prior qa-run mirror — a comment whose body contains `## QA Run Summary` or `### Finding #`. If yes, warn the user: "Linear already has qa-run comments from a previous run, but no local results file exists. Reply `fresh` to start over, or point to an existing `qa-results-*.md` to resume from." Wait for the answer before proceeding.
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
2. **Run together**: present the steps from the plan's table. The user performs them in the browser/BO/Mailpit, or asks Claude to drive via the `chrome-cdp` skill with `--isolated` (sandboxed Chrome on a dedicated profile — same actions a human would do, no shortcuts via JS console, GraphQL, or DB). **When Claude drives, run the scenario in a fresh sub-agent** so its DOM dumps, screenshots, and any source reads stay out of the main context — one sub-agent per scenario, sequential. It returns only the structured outcome: status (pass/fail/skip), a one-line note, a `proof` screenshot path, a `trace` (account used + ordered pages visited, see below), and a finding block (title, severity, repro, expected, observed, root-cause `file:line`, `debug` screenshot paths) when it fails. The orchestrator does all the writing.
   - **Trace (autonomous mode only).** Have the sub-agent return a `trace`: the **account** it logged in as (email/role, from the plan preconditions) and an ordered list of the pages it visited as `action → URL` (or page name when there's no clean URL), covering the navigation that reached the observed outcome. Keep it terse — the path, not a DOM dump. The orchestrator writes it (Step 2.6).
   - **Evidence (autonomous mode only).** Tell the sub-agent to save one key-moment screenshot proving the observed outcome to `tasks/<TASK>/evidence/<scenario-id>.png` (e.g. `tasks/BOF-218/evidence/1.2.png`) via the isolated-mode `cdp.mjs shot <target> <path>` (after `chrome-debug.sh`, with `CDP_PORT_FILE` set — see the `chrome-cdp` skill), for passes and fails alike. `<TASK>` = `SUBISSUE_KEY` (Linear) or the plan's folder name (local). On failure, also save 1–3 debug shots to `<scenario-id>-debug-N.png` in the same dir. It returns these paths in `proof` / `debug`; surfacing them is the orchestrator's job (Step 2.7, Step 3). See [references/linear-evidence.md](references/linear-evidence.md).
3. **Decide outcome and append to results**:
   - Pass → `[x] §X.Y — passed (<short note if useful>)`. The pass must rest on something observed in the browser/UI/email — never on a DB/GraphQL peek. In autonomous mode, append `proof: <path>` to the parens.
   - Fail → `[!] §X.Y — failed → Finding #<n>` + new Finding entry. If the runner is the dev, read the source to root-cause and fill the Finding's **Root cause** line with `file:line` evidence. PM/QA runners leave it blank. In autonomous mode, fill the Finding's **Evidence** line with the proof + debug paths.
   - Skip → `[~] §X.Y — skipped (<reason>)` + Finding tagged `plan-defect` if the plan itself is the problem
4. If a gotcha or recipe surfaced, append a one-liner to § Notes.
5. Write immediately. Don't batch.
6. **Write the trace (autonomous mode only):** append the sub-agent's `trace` to `tasks/<TASK>/qa-trace.md` under a `## §X.Y — <title>` heading. Create the file from the trace template on the first scenario of the run. Append-only, same discipline as `qa-results.md`.
7. **Mirror to Linear (only if `SOURCE=linear` and outcome is Fail or Skip-as-plan-defect):** delegate to `linear-cli` to add a comment on `SUBISSUE_KEY` whose body is the new Finding entry — starting with its `### Finding #<n> …` heading, no machine marker. The heading is what future runs match on. In autonomous mode, pass each debug screenshot as a repeated `--attach <path>` so they land as an end-gallery on the finding comment. If the comment fails (auth, network), print the error and continue — local results stay the source of truth.

## Step 3: End-of-run summary

- Totals: passed / failed / skipped / pending.
- Triage table grouped by severity: `blocker`, `improvement`, `nit`, `plan-defect`.
- Suggest next step based on what's open:
  - Blockers → fix via `/ralph-tui`, then re-run `/qa-run` on the same results file.
  - Plan defects → update via `/qa-plan` (or hand-edit), then re-run.
  - Nits only → ready to flip the PR to ready-for-review.

**Mirror to Linear (only if `SOURCE=linear`):** delegate to `linear-cli` to post the same summary as a single comment on `SUBISSUE_KEY`, starting with the `## QA Run Summary — <KEY>` heading (no machine marker). That heading is the detection signature for future runs. Comment failures don't block — the local results file is the canonical record.

In autonomous mode, give the summary's Scenarios table a **Proof** column. For each row, upload its proof shot first — `URL=$(node scripts/upload-image.mjs <path>)` — then write `![](<URL>)` into the Proof cell, and post the assembled body with `--body-file` (no `--attach`, the images are already in-body). If an upload fails, fall back to a plain `--attach` gallery for that shot. Cell images aren't guaranteed to render in Linear's editor — on the first real run, eyeball the comment and switch Proof cells to the link form `[📷 §N.M](<URL>)` if they don't. Details in [references/linear-evidence.md](references/linear-evidence.md).

## qa-results.md template

```markdown
# QA Results — <plan title>

**Plan:** tasks/<TASK>/qa-plan.md
**Trace (autonomous runs):** tasks/<TASK>/qa-trace.md
**Started:** <date>
**Last run:** <date>

## Status
- [ ] §1.1 — <title>
- [ ] §1.2 — <title>
- [ ] §2.1 — <title>

## Findings

### Finding #1 — <title> — <blocker|improvement|nit|plan-defect>
**Scenario:** §X.Y
**Repro:** <steps observed>
**Expected:** <from plan>
**Observed:** <what happened>
**Root cause:** <dev only — file:line trace explaining why; omit if not investigated>
**Evidence:** <autonomous only — proof: <path>; debug: <path>, <path>

## Notes
- <gotcha or recipe>
```

## qa-trace.md template (autonomous runs only)

```markdown
# QA Trace — <plan title>

Reproduction breadcrumb for autonomous runs: account + pages visited per scenario.
Not the source of truth (qa-results.md is) — this exists to re-walk the same path.

## §1.1 — <title>
**Account:** <email / role used to log in>
**Path:**
1. <action> → <URL or page>
2. <action> → <URL or page>
```

## Rules

- **Plan is immutable.** Never edit `qa-plan-X.md`, and never edit the Linear sub-issue's description either. If the plan is wrong, log a `plan-defect` finding and tell the user to fix it separately (re-run `/qa-plan` for Linear plans).
- **Local results are the source of truth.** Linear comments are a mirror; if they diverge or fail to post, the local `qa-results-X.md` wins. Never re-derive state from Linear comments.
- **Status lines are one line.** Detail goes in Findings.
- **Append-only.** Never rewrite earlier entries. To retry a failed case, the user flips `[!]` to `[ ]` manually, or asks Claude to retry a specific scenario.
- **Browser CDP is OK** (via the `chrome-cdp` skill in `--isolated` mode) for clicking faster than a human, not for bypassing audience constraints. No `evaluate()` shortcuts to read Mongo, no GraphQL fetches, no `localStorage` poking beyond what a normal user does unless the user doing the explicitly allows it to verify a tricky state.
- **Verify in the browser, root-cause in the source.** A pass is only ever earned by something observed in the UI/email — never by reading the DB or code. But once something fails, a dev runner *should* open the source to explain why and cite `file:line`. The constraint is about what proves a pass, not about what you may read to explain a failure.
- **No machine markers in Linear comments.** Mirror comments are plain markdown that reads cleanly in the Linear UI. Detection of prior runs keys off the natural headings (`## QA Run Summary`, `### Finding #N`), so don't prepend HTML-comment signatures.
- **Trace is a reproduction aid, not the record.** `qa-trace.md` is autonomous-mode only — `qa-results.md` stays canonical. If they diverge, results win.
- **One scenario at a time.** Don't pre-execute and dump all results — each step needs human verification before moving on. When Claude drives via sub-agent, that means one sub-agent finishes and is logged before the next is spawned.
