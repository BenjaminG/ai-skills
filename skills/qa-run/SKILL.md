---
name: qa-run
description: >-
  Execute a qa-plan interactively. The plan can live locally (qa-plan-X.md)
  or remotely on Linear (sub-issue created by /qa-plan --linear). Walks
  through each scenario with the user, logs status + findings + notes to a
  fresh timestamped qa-results-<ts>.md per run (multiple coexist in the task
  folder). When the source is Linear, mirrors findings and the final summary
  as comments on the sub-issue. Each run re-verifies every scenario and
  surfaces prior runs' open findings so you confirm whether known bugs are
  fixed. Verification stays browser-only (admin UI + email sandbox);
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

Each run writes its own timestamped results file — `qa-results-<ts>.md` where `<ts>` = `date +%Y%m%d-%H%M%S` (e.g. `qa-results-20260714-153000.md`). The name is sortable, so "the latest run" = the max filename. Multiple runs coexist in the task folder; earlier files are read as history (Step 1) but never rewritten. Legacy `qa-results.md` / `qa-results-X.md` are still *read* as prior history — never written.

### Local path
Use the file directly. Results go in the **same directory** as the plan — e.g. `tasks/BOF-218/qa-plan.md` → `tasks/BOF-218/qa-results-<ts>.md`. `SOURCE=local`.

### Linear key or URL
1. Use the **`linear-cli`** skill to fetch the issue's title and description body. Do not inline CLI flags here — let `linear-cli` handle the mechanics.
2. If the issue title does **not** start with `QA:` it's likely the parent ticket, not the QA sub-issue. Ask `linear-cli` to list sub-issues and pick the one whose title starts with `QA:`.
   - Zero matches → abort: "No `QA: ...` sub-issue found under <KEY>. Run `/qa-plan --linear` first or pass the sub-issue key directly."
   - Multiple matches → list them and ask the user which to use.
3. Persist the description body to `tasks/<SUBISSUE_KEY>/qa-plan.md` (create `tasks/<SUBISSUE_KEY>/` if missing). If the file already exists with different content, ask before overwriting (the user may have local edits).
4. Results go in `tasks/<SUBISSUE_KEY>/` as `qa-results-<ts>.md` (see above). Set `SOURCE=linear` and remember `SUBISSUE_KEY` for Step 2/3 mirroring.

## Step 1: Initialize new run + load prior context

Each invocation is a **fresh full pass** — it always creates a new results file and re-verifies every scenario. Prior runs are read only to *focus* the pass (flag known failures to confirm they're fixed), never to skip scenarios.

**Load prior context:**
- Glob `tasks/<TASK>/qa-results-*.md` (plus legacy `qa-results.md`). Read all matches — the max filename is the latest run.
- Build **`KNOWN_ISSUES`**: for each scenario `§X.Y`, its latest status across the files and any finding still **open** (a finding logged in one run and not marked fixed in a newer one). Record which scenarios *passed* most recently too, so a fresh failure can be flagged as a regression.
- **Linear fresh-clone fallback (best-effort):** if `SOURCE=linear`, no local files exist, but the sub-issue has prior `### Finding #…` comments, read those headings to seed `KNOWN_ISSUES` for **focus only** — read-only, not a status source (local files stay canonical, per Rules).

**Create the new run file** `tasks/<TASK>/qa-results-<ts>.md`:
- From the template below. Set `**Run:** <ts>` and `**Prior runs:** <files read | none>`.
- Pre-populate § Status with one `[ ]` line per scenario (parsed from plan headings `### N.M`).

**Echo the focus banner** (only if `KNOWN_ISSUES` is non-empty):
`N open findings from prior runs to re-verify: §1.2 (<finding title>), §3.1 (<finding title>), …`
Every scenario still runs — the banner directs attention, it does not narrow scope. Then start at §1.1.

## Step 2: Iterate scenarios

For each scenario in plan order — **all of them**; the run file starts empty, so there is nothing to skip:

1. **Announce**: §X.Y title, "How to reach this state", preconditions. If the scenario is in `KNOWN_ISSUES`, frame it as fix-verification: `§X.Y previously failed (Finding: <title>, <prior-ts>) — verify whether it's fixed.`
2. **Run together**: present the steps from the plan's table. The user performs them in the browser/BO/Mailpit, or asks Claude to drive via the `chrome-cdp` skill with `--isolated` (sandboxed Chrome on a dedicated profile — same actions a human would do, no shortcuts via JS console, GraphQL, or DB). **When Claude drives, run the scenario in a fresh sub-agent** so its DOM dumps, screenshots, and any source reads stay out of the main context — one sub-agent per scenario, sequential. It returns only the structured outcome: status (pass/fail/skip), a one-line note, a `proof` screenshot path, a `trace` (account used + ordered pages visited, see below), and a finding block (title, severity, repro, expected, observed, root-cause `file:line`, `debug` screenshot paths) when it fails. The orchestrator does all the writing.
   - **Trace (autonomous mode only).** Have the sub-agent return a `trace`: the **account** it logged in as (email/role, from the plan preconditions) and an ordered list of the pages it visited as `action → URL` (or page name when there's no clean URL), covering the navigation that reached the observed outcome. Keep it terse — the path, not a DOM dump. The orchestrator writes it (Step 2.6).
   - **Evidence (autonomous mode only).** Tell the sub-agent to save one key-moment screenshot proving the observed outcome to `tasks/<TASK>/evidence/<scenario-id>.png` (e.g. `tasks/BOF-218/evidence/1.2.png`) via the isolated-mode `cdp.mjs shot <target> <path>` (after `chrome-debug.sh`, with `CDP_PORT_FILE` set — see the `chrome-cdp` skill), for passes and fails alike. `<TASK>` = `SUBISSUE_KEY` (Linear) or the plan's folder name (local). On failure, also save 1–3 debug shots to `<scenario-id>-debug-N.png` in the same dir. It returns these paths in `proof` / `debug`; surfacing them is the orchestrator's job (Step 2.7, Step 3). See [references/linear-evidence.md](references/linear-evidence.md).
3. **Decide outcome and append to results** (when the scenario is in `KNOWN_ISSUES`, note the prior relationship in the status line, as shown):
   - Pass → `[x] §X.Y — passed (<short note if useful>)`. The pass must rest on something observed in the browser/UI/email — never on a DB/GraphQL peek. In autonomous mode, append `proof: <path>` to the parens. If it was a known failure → `[x] §X.Y — passed (fixed: was <finding-ref> @ <prior-ts>)`.
   - Fail → `[!] §X.Y — failed → Finding #<n>` + new Finding entry. If the runner is the dev, read the source to root-cause and fill the Finding's **Root cause** line with `file:line` evidence. PM/QA runners leave it blank. In autonomous mode, fill the Finding's **Evidence** line with the proof + debug paths. If it was a known failure → append `(still failing — was <finding-ref> @ <prior-ts>)`; if it passed in a prior run → append `(regression — passed @ <prior-ts>)`. Set the new Finding's **Prior:** line accordingly.
   - Skip → `[~] §X.Y — skipped (<reason>)` + Finding tagged `plan-defect` if the plan itself is the problem
4. If a gotcha or recipe surfaced, append a one-liner to § Notes.
5. Write immediately. Don't batch.
6. **Write the trace (autonomous mode only):** append the sub-agent's `trace` to `tasks/<TASK>/qa-trace.md` under a `## §X.Y — <title>` heading. Create the file from the trace template on the first scenario of the run. Append-only, same discipline as the run file.
7. **Mirror to Linear (only if `SOURCE=linear` and outcome is Fail or Skip-as-plan-defect):** delegate to `linear-cli` to add a comment on `SUBISSUE_KEY` whose body is the new Finding entry — starting with its `### Finding #<n> …` heading, no machine marker. The heading is what future runs match on. In autonomous mode, pass each debug screenshot as a repeated `--attach <path>` so they land as an end-gallery on the finding comment. If the comment fails (auth, network), print the error and continue — local results stay the source of truth.
   - **Known issue now fixed:** when a scenario in `KNOWN_ISSUES` passes this run, optionally add a one-line resolution comment on the sub-issue (e.g. `Finding "<title>" verified fixed in run <ts>.`). Best-effort, non-blocking — a failed post never blocks the run.

## Step 3: End-of-run summary

- Totals: passed / failed / skipped / pending.
- **Fix-verification rollup** (only if `KNOWN_ISSUES` was non-empty): of the prior open findings, how many are **fixed** / **still open** / **newly regressed** this run — e.g. `Prior issues: 2 fixed, 1 still open (§3.1), 1 regression (§1.2).`
- Triage table grouped by severity: `blocker`, `improvement`, `nit`, `plan-defect`.
- Suggest next step based on what's open:
  - Blockers → fix via `/ralph-tui`, then re-run `/qa-run` (a fresh timestamped run picks up the prior findings automatically).
  - Plan defects → update via `/qa-plan` (or hand-edit), then re-run.
  - Nits only → ready to flip the PR to ready-for-review.

**Mirror to Linear (only if `SOURCE=linear`):** delegate to `linear-cli` to post the same summary as a single comment on `SUBISSUE_KEY`, starting with the `## QA Run Summary — <KEY> @ <ts>` heading (no machine marker). The `## QA Run Summary` prefix is the detection signature for future runs; the `<ts>` keeps multiple run summaries distinguishable. Comment failures don't block — the local results file is the canonical record.

In autonomous mode, give the summary's Scenarios table a **Proof** column. For each row, upload its proof shot first — `URL=$(node scripts/upload-image.mjs <path>)` — then write `![](<URL>)` into the Proof cell, and post the assembled body with `--body-file` (no `--attach`, the images are already in-body). If an upload fails, fall back to a plain `--attach` gallery for that shot. Cell images aren't guaranteed to render in Linear's editor — on the first real run, eyeball the comment and switch Proof cells to the link form `[📷 §N.M](<URL>)` if they don't. Details in [references/linear-evidence.md](references/linear-evidence.md).

## qa-results-<ts>.md template

```markdown
# QA Results — <plan title>

**Plan:** tasks/<TASK>/qa-plan.md
**Trace (autonomous runs):** tasks/<TASK>/qa-trace.md
**Run:** <ts>
**Prior runs:** <qa-results-*.md files read | none>

## Status
- [ ] §1.1 — <title>
- [ ] §1.2 — <title>
- [ ] §2.1 — <title>

## Findings

### Finding #1 — <title> — <blocker|improvement|nit|plan-defect>
**Scenario:** §X.Y
**Prior:** <finding-ref @ prior-ts if this recurs from an earlier run; omit for new findings>
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
Not the source of truth (the run's qa-results-<ts>.md is) — this exists to re-walk the same path.

## §1.1 — <title>
**Account:** <email / role used to log in>
**Path:**
1. <action> → <URL or page>
2. <action> → <URL or page>
```

## Rules

- **Plan is immutable.** Never edit `qa-plan-X.md`, and never edit the Linear sub-issue's description either. If the plan is wrong, log a `plan-defect` finding and tell the user to fix it separately (re-run `/qa-plan` for Linear plans).
- **Local results are the source of truth.** The set of `qa-results-*.md` files in the task folder is the record; the **latest** file (max timestamp) is current state, older files are history. Linear comments are a mirror; if they diverge or fail to post, the local files win. Never re-derive state from Linear comments.
- **Status lines are one line.** Detail goes in Findings.
- **One file per run, append-only within it.** Each invocation owns one `qa-results-<ts>.md` — never edit an earlier run's file. Within the current run's file, only append; never rewrite earlier entries. To re-test a scenario, start a fresh run (`/qa-run` again) — it re-verifies everything and flags what previously failed.
- **Browser CDP is OK** (via the `chrome-cdp` skill in `--isolated` mode) for clicking faster than a human, not for bypassing audience constraints. No `evaluate()` shortcuts to read Mongo, no GraphQL fetches, no `localStorage` poking beyond what a normal user does unless the user doing the explicitly allows it to verify a tricky state.
- **Verify in the browser, root-cause in the source.** A pass is only ever earned by something observed in the UI/email — never by reading the DB or code. But once something fails, a dev runner *should* open the source to explain why and cite `file:line`. The constraint is about what proves a pass, not about what you may read to explain a failure.
- **No machine markers in Linear comments.** Mirror comments are plain markdown that reads cleanly in the Linear UI. Detection of prior runs keys off the natural headings (`## QA Run Summary`, `### Finding #N`), so don't prepend HTML-comment signatures.
- **Trace is a reproduction aid, not the record.** `qa-trace.md` is autonomous-mode only — the run's `qa-results-<ts>.md` stays canonical. If they diverge, results win.
- **One scenario at a time.** Don't pre-execute and dump all results — each step needs human verification before moving on. When Claude drives via sub-agent, that means one sub-agent finishes and is logged before the next is spawned.
