---
name: qa-run
description: >-
  Execute a qa-plan interactively, autonomously driving Chrome via chrome-cdp
  by default. Each run is posted as its own sub-issue/file under the plan
  (--tracker linear|github|local), re-verifies every scenario, and surfaces
  prior runs' open findings. A persisted playbook (site knowledge + per-scenario
  fast paths) lets later runs replay known scenarios in one batched command
  instead of re-exploring. This skill should be used to run a manual QA pass
  against a plan produced by /qa-plan, whether the runner is the dev
  (dogfooding before handoff) or the PM/QA tester.
argument-hint: "[plan-ref] [--tracker linear|github|local]"
---

# QA Run

**Verification is browser-only.** Confirm a scenario by what a user observes
in the browser / admin UI / email sandbox — never mark a step passed because a
DB query, GraphQL response, or log line says so. If a step can *only* be
confirmed via terminal/DB/GraphQL, that's a plan-defect: log it, don't fake the
pass. Root-causing is different: once a step fails, a dev runner should read
the source to explain why and cite `file:line` in the Finding — that's an
asset, not a violation.

## Step 0: Resolve tracker + locate the plan

Parse `$ARGUMENTS`. Strip a trailing `--tracker linear|github|local` into
`TRACKER`; the remainder is the plan reference. Without the flag, infer from
the reference's shape:

| plan-ref | TRACKER |
|---|---|
| `^[A-Z]+-\d+$` or contains `linear.app/` | `linear` |
| `^#?\d+$` or `github.com/…/issues/N` | `github` |
| a path, or no arg | `local` |

No arg + `local` → most recent `tasks/*/qa-plan.md` by mtime. None found → abort.

Validate the precondition **before** doing any work:

| TRACKER | Precondition |
|---|---|
| `linear` | `linear` CLI installed; delegate all Linear calls to the **`linear-cli`** skill |
| `github` | `gh repo view --json nameWithOwner` succeeds |
| `local` | none |

### Find the plan issue / file

- **linear**: the ref is a Linear key/URL. If the issue title doesn't start
  with `QA:`, it's the parent — list sub-issues and pick the one titled
  `QA: …` (zero → abort telling the user to run `/qa-plan --linear`; multiple →
  ask). Persist its description to `tasks/<SUBISSUE_KEY>/qa-plan.md` (ask
  before overwriting local edits). `TASK = SUBISSUE_KEY`.
- **github**: the ref is an issue number/URL. `gh issue view <n> --json title,body`.
  If the title doesn't start with `QA:`, treat `<n>` as the parent and find its
  `QA: …` sub-issue via `subIssues` (GraphQL, see Step 2). Persist the body to
  `tasks/pr-<n>/qa-plan.md`. `TASK = pr-<n>`.
- **local**: use the file directly. `TASK` = its parent folder name.

## Step 1: Load prior context

Each invocation is a fresh full pass — it re-verifies every scenario. Prior
runs are read only to *focus* the pass, never to skip scenarios.

- **linear**: list the plan issue's children via `linear-cli`, take the newest
  3 titled `QA Run *`, read their descriptions.
- **github**: `gh api graphql` for `issue(number:N){subIssues(last:3){nodes{number,title,body}}}`.
- **local**: glob `tasks/<TASK>/qa-results-*.md`, read all matches.

From those bodies build **`KNOWN_ISSUES`**: for each `§X.Y`, its latest status
and any finding still open (logged in one run, not marked fixed in a newer
one). Record recent passes too, so a fresh failure can be flagged a regression.

**Echo the focus banner** (only if `KNOWN_ISSUES` is non-empty): `N open
findings from prior runs to re-verify: §1.2 (<title>), …`. Every scenario still
runs — the banner directs attention, it doesn't narrow scope.

**Load the playbook:**
- Site level: read `~/.claude/qa-playbook/<repo>.md` (`<repo>` =
  `basename "$(git rev-parse --show-toplevel)"`). Missing = empty, not an error.
- Scenario level: read the `## QA Playbook` comment on the plan issue
  (`linear`/`github`) or `tasks/<TASK>/qa-playbook.md` (`local`). Missing = empty.

## Step 2: Create the run record

Created in **Todo**, assigned to the runner, so the tracker shows every run's
lifecycle end to end — Todo → In Progress (Step 3) → closed (Step 4).

- **linear**: `linear issue create --parent "$QA_KEY" --title "QA Run <ts>" --assignee self --state unstarted --description-file $TMP` (`<ts>` = `date +%Y%m%d-%H%M%S`; `unstarted` is the state *type* — Todo in Linear's default template — not a team-specific state name, so this holds regardless of the team's actual label).
- **github**: `gh label create qa-run --color 5319E7 2>/dev/null || true`, then
  `gh issue create --title "QA Run <ts>" --label qa-run --assignee @me --body-file $TMP`
  (GitHub issues have no Todo/In-Progress distinction without a Projects board,
  out of scope here — the issue is simply open, assigned, for the run's
  duration, then closed in Step 4), then nest it under the plan issue:
  ```bash
  gh api graphql -f query='mutation($p:ID!,$c:ID!){addSubIssue(input:{issueId:$p,subIssueId:$c}){clientMutationId}}' -F p="$PARENT_NODE_ID" -F c="$RUN_NODE_ID"
  ```
  (node ids via `gh api graphql -f query='{repository(owner:"O",name:"R"){issue(number:N){id}}}'`).
  If `addSubIssue` fails (org without sub-issues enabled), fall back to a
  comment on the plan issue linking the run issue and say so.
- **local**: write `tasks/<TASK>/qa-results-<ts>.md` from the template below.

The body/file starts from the template in **Report format** below, with one
`[ ]` status line per scenario (parsed from the plan's `### N.M` headings).

**Resolve `$T` once** (pre-flight, shared by every scenario): `chrome-debug.sh`,
then `cdp.mjs list`, confirming the top target's title/URL is actually the app
under test — a fixture that collides or short-circuits burns a whole pass,
catch it here as a plan-defect rather than mark passes against it.

## Step 3: Iterate scenarios

**Move the run to In Progress** before the first scenario:
`linear issue update <RUN_KEY> --state started` (`github`/`local`: no-op —
the issue is already open / the file already exists).

For each scenario in plan order — all of them, nothing is skipped, unless the
user stops the run early after a blocker (see Step 4):

1. **Announce**: §X.Y title, preconditions. If in `KNOWN_ISSUES`, frame as
   fix-verification: `§X.Y previously failed (Finding: <title>, <prior-ts>) — verify whether it's fixed.`
2. **Spawn one sub-agent** (sequential — never parallel) following
   [references/scenario-agent.md](references/scenario-agent.md): it replays the
   scenario's playbook block if one exists, falls back to interactive
   exploration otherwise, and returns the structured payload described there.
3. **Upload the evidence** (`--tracker linear` only — `github`/`local` keep the
   local paths as-is): for the payload's `proof`, run
   `URL=$(node scripts/upload-image.mjs <proof>)`. Use `$URL` — never the local
   path — everywhere the run doc cites that proof. If the upload exits non-zero,
   cite the local path and note `(upload failed)`; never abort the run for it.
   `debug` shots are not uploaded here — they go to the finding comment in Step 5.
4. **Decide outcome, annotate with prior-run relation, append to the run doc:**
   - Pass → `[x] §X.Y — passed (<note>, [📷 §X.Y](<proof URL or path>))`. If it was a known
     failure: `(fixed: was <finding-ref> @ <prior-ts>)`.
   - Fail → `[!] §X.Y — failed → Finding #<n>` + a Finding entry (dev runner
     fills **Root cause** with `file:line`; PM/QA leaves it blank). If it was a
     known failure: `(still failing — was <finding-ref> @ <prior-ts>)`; if it
     passed previously: `(regression — passed @ <prior-ts>)`.
   - Skip → `[~] §X.Y — skipped (<reason>)`, Finding tagged `plan-defect` if the
     plan itself is the problem.
5. **Rewrite the run body/file now** (never batch): `linear issue update
   <RUN_KEY> --description-file $TMP` / `gh issue edit <n> --body-file $TMP` /
   overwrite the local file. **If the push fails** (auth, network), print the
   error, write the doc to `tasks/<TASK>/qa-results-<ts>.md` as a crash file,
   and continue the run — a 40-minute pass must not die to a token expiry.
6. **Accumulate the playbook delta** from the sub-agent's payload (don't write
   yet — merged once at end of run, Step 4).

## Step 4: End-of-run summary, close-out + playbook merge

This step runs on **every** exit path — all scenarios completed, or the user
stopped the run early after a blocker finding — so the run issue never sits
abandoned in "In Progress". Run it against whatever scenarios actually
executed.

- Totals: passed / failed / skipped / pending (pending = not reached, only
  possible on an early stop).
- **Fix-verification rollup** (only if `KNOWN_ISSUES` was non-empty): `Prior
  issues: 2 fixed, 1 still open (§3.1), 1 regression (§1.2).`
- Triage table grouped by severity: `blocker`, `improvement`, `nit`, `plan-defect`.
- Next step: blockers → fix, re-run; plan-defects → fix the plan, re-run;
  nits only → ready for review.

**Close the run:** `linear issue update <RUN_KEY> --state completed` /
`gh issue close <n>` (`local`: nothing to close). This applies whether the run
finished normally or was stopped early on a blocking finding — the run itself
completed its job (it produced a result), so it closes rather than staying open.

**Attach the debug shots** for each finding (`--tracker linear`): post the
finding's gallery with `linear issue comment add <RUN_KEY> --attach shot.png`
(repeatable) — `--attach` always appends the images at the end of the comment,
which is exactly what a gallery wants. Under `github`/`local` the run doc's
local `tasks/<TASK>/evidence/` paths are the record. See
[references/linear-evidence.md](references/linear-evidence.md) for the
mechanics and the inline-image alternative.

**Merge the playbook** (once, here — not per scenario):
- Site: append each returned `playbook.site` line to
  `~/.claude/qa-playbook/<repo>.md` under its section, skipping near-duplicates.
- Scenario: splice each returned `playbook.scenario` block into the single
  `## QA Playbook` comment/file, applying the staleness rule from
  [references/playbook.md](references/playbook.md#learning): a `stale:*` replay
  with a corrected block replaces it (`Stale: 0`); a `stale:*` replay with no fix
  keeps the old block and bumps `Stale: 1`; a block already at `Stale: 1` that
  goes stale again is **deleted**. Write back with a single
  `comment update` / `issue edit` / file overwrite.

## Report format (run body / qa-results-<ts>.md)

```markdown
# QA Results — <plan title>

**Plan:** <plan issue URL or tasks/<TASK>/qa-plan.md>
**Run:** <ts>

## Status
- [ ] §1.1 — <title>
- [ ] §1.2 — <title>

<!-- proof links are Linear assetUrls under --tracker linear, local paths otherwise -->

## Findings

### Finding #1 — <title> — <blocker|improvement|nit|plan-defect>
**Scenario:** §X.Y
**Prior:** <finding-ref @ prior-ts if recurring; omit for new findings>
**Repro:** <steps observed>
**Expected:** <from plan>
**Observed:** <what happened>
**Root cause:** <dev only — file:line; omit if not investigated>
**Evidence:** proof: <assetUrl under linear, else path>; debug: <path>, <path>

## Notes
- <gotcha not worth a playbook entry>
```

## Rules

- **Plan is immutable.** Never edit the plan file or issue description. The
  `## QA Playbook` comment on the same issue is **mutable and not part of the
  plan** — it's expected to change every run. If the plan itself is wrong, log
  a `plan-defect` finding and tell the user to fix it separately.
- **The tracker is the record.** Under `linear`/`github`, the run sub-issue is
  canonical; under `local`, the file is. Never re-derive state from anything else.
- **Never edit a previous run's issue/file.** Each invocation owns one run
  record; within the current run, rewrite the whole body on each scenario
  (Step 3.4) rather than appending — the body is a live document, not a log.
- **Status lines are one line.** Detail goes in Findings.
- **Verify in the browser, root-cause in the source.** A pass rests only on
  something observed in the UI/email — never a DB/GraphQL peek. Once something
  fails, reading the source to explain why (with `file:line`) is encouraged.
- **Browser CDP is OK** (via `chrome-cdp --isolated`) for clicking faster than a
  human, not for bypassing audience constraints. No `evaluate()` shortcuts to
  read the DB, no GraphQL fetches, no `localStorage` poking beyond what a
  normal user does, unless the user explicitly allows it to verify a tricky state.
- **One scenario at a time, sequential sub-agents.** Each finishes and is
  logged before the next is spawned.
- **A failing scenario never contributes a `Verify` fast path** — see
  [references/playbook.md](references/playbook.md#learning). It can still
  contribute `Reach` (the precondition) plus site notes.
- **The run issue's lifecycle is Todo → In Progress → closed, every time.**
  Assigned to the runner at creation (Step 2). Never leave it "In Progress"
  after the run stops — Step 4 runs, and the issue closes, on any exit path.
